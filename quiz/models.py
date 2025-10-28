import random
import string
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone
from .image_utils import resize_and_optional_crop

AVATARS = [
    "🎃",  # pumpkin
    "👻",  # ghost
    "🧙‍♀️",  # witch
    "🧛‍♂️",  # vampire
    "🧟‍♀️",  # zombie
    "🧚‍♂️",  # dark fairy
    "🦇",  # bat
    "🕷️",  # spider
    "🕸️",  # web
    "💀",  # skull
    "☠️",  # skull & crossbones
    "🩸",  # blood drop
    "🧝‍♂️",  # creepy elf
    "🦉",  # owl (night creature)
    "🐈‍⬛",  # black cat
    "🕯️",  # candle
]

PHASE_WAITING = "WAITING"
PHASE_ANSWER  = "ANSWER"
PHASE_REVEAL  = "REVEAL"
PHASE_FINISHED = "FINISHED"

PHASE_CHOICES = [
    (PHASE_WAITING, "Waiting"),
    (PHASE_ANSWER, "Answering"),
    (PHASE_REVEAL, "Reveal"),
    (PHASE_FINISHED, "Finished"),
]

ANSWER_SECONDS = 10
REVEAL_SECONDS = 10

def generate_6_digit_code():
    return ''.join(random.choices(string.digits, k=6))

class Quiz(models.Model):
    # ...existing fields...
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='quizzes', null=True, blank=True)
    title = models.CharField(max_length=200)
    access_code = models.CharField(max_length=6, unique=True, validators=[RegexValidator(r'^\d{6}$')], editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    # NEW: live game state
    phase = models.CharField(max_length=10, choices=PHASE_CHOICES, default=PHASE_WAITING)
    current_index = models.PositiveIntegerField(default=0)  # question index
    phase_started_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def _assign_code_if_needed(self):
        if self.access_code:
            return
        for _ in range(10):
            code = generate_6_digit_code()
            if not Quiz.objects.filter(access_code=code).exists():
                self.access_code = code
                return
        raise ValidationError("Could not generate a unique access code. Try again.")

    def seconds_in_phase(self):
        if not self.phase_started_at:
            return 0
        return max(0, int((timezone.now() - self.phase_started_at).total_seconds()))

    def phase_remaining(self):
        if self.phase == PHASE_ANSWER:
            return max(0, ANSWER_SECONDS - self.seconds_in_phase())
        if self.phase == PHASE_REVEAL:
            return max(0, REVEAL_SECONDS - self.seconds_in_phase())
        return 0
    
    def has_rounds(self) -> bool:
        return self.rounds.exists()

    def questions_in_round(self, round_: "Round"):
        return self.questions.filter(round=round_).order_by("order", "id")

    def question_count(self):
        return self.questions.count()

    def current_question(self):
        qs = list(self.questions.select_related().prefetch_related("options"))
        if 0 <= self.current_index < len(qs):
            return qs[self.current_index]
        return None

    def _advance_to_reveal(self):
        self.phase = PHASE_REVEAL
        self.phase_started_at = timezone.now()
        # update scores for this question
        q = self.current_question()
        if q:
            # +1 for each attempt that picked correct option
            correct_ids = set(q.options.filter(is_correct=True).values_list("id", flat=True))
            for ans in Answer.objects.filter(question=q, attempt__quiz=self):
                if ans.selected_option_id in correct_ids:
                    Attempt.objects.filter(id=ans.attempt_id).update(score=models.F("score") + 1)

    def _advance_to_next_question_or_finish(self):
        self.current_index += 1
        if self.current_index >= self.question_count():
            self.phase = PHASE_FINISHED
            self.finished_at = timezone.now()
        else:
            self.phase = PHASE_ANSWER
            self.phase_started_at = timezone.now()

    def maybe_tick(self):
        """
        Call this on every request touching the quiz.
        Moves from ANSWER->REVEAL after 30s, and REVEAL->next/finish after 30s.
        """
        if self.phase == PHASE_ANSWER and self.seconds_in_phase() >= ANSWER_SECONDS:
            self._advance_to_reveal()
            self.save(update_fields=["phase", "phase_started_at"])
        elif self.phase == PHASE_REVEAL and self.seconds_in_phase() >= REVEAL_SECONDS:
            prev_fields = ["phase", "phase_started_at", "current_index", "finished_at"]
            self._advance_to_next_question_or_finish()
            self.save(update_fields=prev_fields)

    def clean(self):
        if not self.access_code:
            self._assign_code_if_needed()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.access_code})"
    

class Round(models.Model):
    quiz = models.ForeignKey(
        "Quiz", on_delete=models.CASCADE, related_name="rounds"
    )
    name = models.CharField(max_length=200)  # required
    description = models.TextField(blank=True)  # optional
    image = models.ImageField(upload_to="rounds/", blank=True, null=True)  # optional
    order = models.PositiveIntegerField(default=0, help_text="Display order")

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "name"], name="uniq_round_name_per_quiz"
            )
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image:
            # keep aspect ratio; don't force crop for round cover art
            resize_and_optional_crop(
                self.image, max_size=(1600, 1600), crop_ratio=None, quality=85, format_hint="JPEG"
            )
            super().save(update_fields=["image"])

    def __str__(self):
        return f"Round: {self.name} ({self.quiz})"

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    round = models.ForeignKey(
        Round,
        on_delete=models.SET_NULL,
        related_name="questions",
        blank=True,
        null=True,
        help_text="Optional: assign this question to a round.",
    )
    
    text = models.TextField(blank=True)
    image = models.ImageField(upload_to='questions/', blank=True, null=True)
    explanation = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0, help_text="Display order")

    class Meta:
        ordering = ['order', 'id']

    def clean(self):
        if not self.text and not self.image:
            raise ValidationError("Provide question text and/or an image.")

        if self.round and self.round.quiz_id != self.quiz_id:
            raise ValidationError("Question's round must belong to the same quiz.")
        
        # Validate answer options rule when question already has options in memory
        options = list(self.options.all()) if self.pk else []
        if options:
            if len(options) != 4:
                raise ValidationError("Each question must have exactly 4 answer options.")
            if sum(1 for o in options if o.is_correct) != 1:
                raise ValidationError("Exactly one answer option must be marked correct.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # save first to ensure file exists
        if self.image:
            # Max 1600x1600, keep aspect, no forced crop so diagrams aren't chopped
            resize_and_optional_crop(self.image, max_size=(1600,1600), crop_ratio=None, quality=85, format_hint="JPEG")
            super().save(update_fields=["image"])  # persist optimized file

    def __str__(self):
        r = f" • {self.round.name}" if self.round_id else ""
        return f"Q{self.pk} in {self.quiz}{r}"

class AnswerOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='options/', blank=True, null=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def clean(self):
        if not self.text and not self.image:
            raise ValidationError("Provide either option text or an image.")
        if self.text and self.image:
            raise ValidationError("Use text OR image for an option, not both.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image:
            resize_and_optional_crop(self.image, max_size=(1200,1200), crop_ratio=(4,3), quality=85, format_hint="JPEG")
            super().save(update_fields=["image"])

    def __str__(self):
        prefix = "✓ " if self.is_correct else ""
        return f"{prefix}Option {self.pk} for Q{self.question_id}"

class Attempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    name = models.CharField(max_length=100, blank=True)  # optional nickname
    avatar = models.CharField(max_length=32, blank=True)  
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Attempt {self.pk} on {self.quiz}"

class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.CASCADE)
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True) 
    
    class Meta:
        unique_together = ('attempt', 'question')

    def is_correct(self):
        return self.selected_option.is_correct
