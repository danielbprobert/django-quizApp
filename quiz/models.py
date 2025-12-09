import random
import string
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone
from .image_utils import resize_and_optional_crop

AVATARS = [
    "🎄",  # Christmas tree
    "🎅",  # Santa Claus
    "🤶",  # Mrs Claus
    "🧑‍🎄",  # festive person/Santa variant
    "🦌",  # reindeer
    "🧝‍♀️",  # Christmas elf (female)
    "🧝‍♂️",  # Christmas elf (male)
    "☃️",  # snowman
    "⛄",  # snowman without snow
    "❄️",  # snowflake
    "🌟",  # shining star
    "✨",  # sparkles
    "🕯️",  # candle
    "🎁",  # present
    "🧦",  # stocking
    "🧣",  # scarf
    "🧤",  # mittens
    "🧊",  # ice block
    "🎀",  # ribbon/bow
    "🍪",  # cookie (Santa snack)
    "🥛",  # milk (for Santa)
    "🍫",  # hot chocolate theme
    "🍰",  # yule cake slice
    "🍬",  # sweet
    "🍭",  # candy
    "🍫",  # chocolate bar
    "🍩",  # festive doughnut
    "🫖",  # warm winter tea
    "🧁",  # cupcake (festive)
    "🧇",  # warm winter waffles
    "🦙",  # winter llama
    "🦊",  # snowy fox
    "🦢",  # swan (12 days of Christmas)
    "🕊️",  # peaceful dove
    "🪽",  # angel wings
    "👼",  # Christmas angel
    "🎶",  # carols/music
    "🎵",  # musical note
    "🔔",  # jingle bell
    "🛷",  # sleigh
    "🏔️",  # snowy mountains
    "🏠",  # warm festive home
    "🛍️",  # Christmas shopping bags
    "🏡",  # snow-covered house
    "🌲",  # evergreen
    "🏙️",  # snowy city
    "⛪",  # Christmas church
    "🕯️",  # Advent candle
    "🧨",  # festive sparkle pop
    "🪩",  # glitter ball
    "🎠",  # festive fairground horse
    "🎆",  # fireworks (New Year)
    "🎇",  # sparkler
    "🥂",  # New Year celebration toast
]

PHASE_WAITING = "WAITING"
PHASE_ANSWER = "ANSWER"
PHASE_REVEAL = "REVEAL"
PHASE_ROUND_BREAK = "ROUND_BREAK"
PHASE_FINISHED = "FINISHED"

PHASE_CHOICES = [
    (PHASE_WAITING, "Waiting"),
    (PHASE_ANSWER, "Answering"),
    (PHASE_REVEAL, "Reveal"),
    (PHASE_ROUND_BREAK, "Round break"),
    (PHASE_FINISHED, "Finished"),
]

# Global defaults – used when a question does not override them
ANSWER_SECONDS = 40
REVEAL_SECONDS = 40


def generate_6_digit_code():
    return "".join(random.choices(string.digits, k=6))


class Quiz(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
        related_name="quizzes",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    access_code = models.CharField(
        max_length=6,
        unique=True,
        validators=[RegexValidator(r"^\d{6}$")],
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    # live game state
    phase = models.CharField(
        max_length=20, choices=PHASE_CHOICES, default=PHASE_WAITING
    )
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
        return max(
            0, int((timezone.now() - self.phase_started_at).total_seconds())
        )

    def _get_phase_durations(self):
        """
        Returns (answer_seconds, reveal_seconds) for the CURRENT question.

        If the question has custom values set, those take precedence.
        Otherwise, falls back to the global defaults ANSWER_SECONDS / REVEAL_SECONDS.
        """
        q = self.current_question()
        answer = ANSWER_SECONDS
        reveal = REVEAL_SECONDS
        if q is not None:
            if q.answer_seconds is not None:
                answer = q.answer_seconds
            if q.reveal_seconds is not None:
                reveal = q.reveal_seconds
        return answer, reveal

    def _round_break_seconds(self):
        """
        If we are at the end of a round that has a pause configured and
        there is a following question, return the pause length in seconds.
        Otherwise returns 0.
        """
        q = self.current_question()
        if not q or not q.round_id:
            return 0

        qs = list(self.questions.order_by("order", "id"))
        if self.current_index >= len(qs) - 1:
            # last question overall – don't pause, go to finished
            return 0

        next_q = qs[self.current_index + 1]
        if next_q.round_id == q.round_id:
            # still in same round
            return 0

        # we've just finished the last question of a round and another question follows
        return q.round.pause_seconds or 0

    def phase_remaining(self):
        answer_secs, reveal_secs = self._get_phase_durations()
        if self.phase == PHASE_ANSWER:
            return max(0, answer_secs - self.seconds_in_phase())
        if self.phase == PHASE_REVEAL:
            return max(0, reveal_secs - self.seconds_in_phase())
        if self.phase == PHASE_ROUND_BREAK:
            break_secs = self._round_break_seconds()
            return max(0, break_secs - self.seconds_in_phase())
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
            correct_ids = set(
                q.options.filter(is_correct=True).values_list("id", flat=True)
            )
            for ans in Answer.objects.filter(question=q, attempt__quiz=self):
                if ans.selected_option_id in correct_ids:
                    Attempt.objects.filter(id=ans.attempt_id).update(
                        score=models.F("score") + 1
                    )

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

        Moves between phases based on the current question's configured
        durations (or the global defaults), and inserts round breaks
        where configured on the Round.
        """
        answer_secs, reveal_secs = self._get_phase_durations()

        if self.phase == PHASE_ANSWER and self.seconds_in_phase() >= answer_secs:
            # Answer time over → reveal
            self._advance_to_reveal()
            self.save(update_fields=["phase", "phase_started_at"])

        elif self.phase == PHASE_REVEAL and self.seconds_in_phase() >= reveal_secs:
            # Reveal time over → either round break or next question/finish
            break_secs = self._round_break_seconds()
            if break_secs > 0:
                self.phase = PHASE_ROUND_BREAK
                self.phase_started_at = timezone.now()
                self.save(update_fields=["phase", "phase_started_at"])
            else:
                prev_fields = [
                    "phase",
                    "phase_started_at",
                    "current_index",
                    "finished_at",
                ]
                self._advance_to_next_question_or_finish()
                self.save(update_fields=prev_fields)

        elif self.phase == PHASE_ROUND_BREAK:
            break_secs = self._round_break_seconds()
            # if for some reason break_secs is 0, just advance immediately
            if self.seconds_in_phase() >= break_secs:
                prev_fields = [
                    "phase",
                    "phase_started_at",
                    "current_index",
                    "finished_at",
                ]
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
    image = models.ImageField(
        upload_to="rounds/", blank=True, null=True
    )  # optional
    order = models.PositiveIntegerField(default=0, help_text="Display order")

    # pause between this round and the next, in seconds
    pause_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Pause after this round (in seconds) before the next question starts. "
            "Leave blank or 0 for no pause."
        ),
    )

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
                self.image,
                max_size=(1600, 1600),
                crop_ratio=None,
                quality=85,
                format_hint="JPEG",
            )
            super().save(update_fields=["image"])

    def __str__(self):
        return f"Round: {self.name} ({self.quiz})"


class Question(models.Model):
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="questions"
    )
    round = models.ForeignKey(
        Round,
        on_delete=models.SET_NULL,
        related_name="questions",
        blank=True,
        null=True,
        help_text="Optional: assign this question to a round.",
    )

    text = models.TextField(blank=True)
    image = models.ImageField(upload_to="questions/", blank=True, null=True)
    explanation = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0, help_text="Display order")

    # per-question timings (optional overrides)
    answer_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Custom answer time in seconds for this question. "
            "Leave blank to use the quiz default."
        ),
    )
    reveal_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Custom reveal time in seconds for this question. "
            "Leave blank to use the quiz default."
        ),
    )

    # NEW: special prize icon
    has_special_icon = models.BooleanField(
        default=False,
        help_text="Show a clickable special prize icon on this question.",
    )
    special_icon = models.CharField(
        max_length=32,
        blank=True,
        help_text="Emoji or short text to use for the special icon (if enabled).",
    )

    class Meta:
        ordering = ["order", "id"]

    def clean(self):
        if not self.text and not self.image:
            raise ValidationError("Provide question text and/or an image.")

        if self.round and self.round.quiz_id != self.quiz_id:
            raise ValidationError("Question's round must belong to the same quiz.")

        if self.has_special_icon and not self.special_icon:
            raise ValidationError(
                "Provide a special icon (emoji or short text) when enabling the special icon."
            )

        # Validate answer options rule when question already has options in memory
        options = list(self.options.all()) if self.pk else []
        if options:
            if len(options) != 4:
                raise ValidationError(
                    "Each question must have exactly 4 answer options."
                )
            if sum(1 for o in options if o.is_correct) != 1:
                raise ValidationError(
                    "Exactly one answer option must be marked correct."
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # save first to ensure file exists
        if self.image:
            # Max 1600x1600, keep aspect, no forced crop so diagrams aren't chopped
            resize_and_optional_crop(
                self.image,
                max_size=(1600, 1600),
                crop_ratio=None,
                quality=85,
                format_hint="JPEG",
            )
            super().save(update_fields=["image"])  # persist optimised file

    def __str__(self):
        r = f" • {self.round.name}" if self.round_id else ""
        return f"Q{self.pk} in {self.quiz}{r}"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to="options/", blank=True, null=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def clean(self):
        if not self.text and not self.image:
            raise ValidationError("Provide either option text or an image.")
        if self.text and self.image:
            raise ValidationError("Use text OR image for an option, not both.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image:
            resize_and_optional_crop(
                self.image,
                max_size=(1200, 1200),
                crop_ratio=(4, 3),
                quality=85,
                format_hint="JPEG",
            )
            super().save(update_fields=["image"])

    def __str__(self):
        prefix = "✓ " if self.is_correct else ""
        return f"{prefix}Option {self.pk} for Q{self.question_id}"


class Attempt(models.Model):
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="attempts"
    )
    name = models.CharField(max_length=100, blank=True)  # optional nickname
    avatar = models.CharField(max_length=32, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Attempt {self.pk} on {self.quiz}"


class Answer(models.Model):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.CASCADE)
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("attempt", "question")

    def is_correct(self):
        return self.selected_option.is_correct


# NEW: log of special icon clicks
class SpecialClick(models.Model):
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="special_clicks"
    )
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="special_clicks"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="special_clicks"
    )
    clicked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"SpecialClick by {self.attempt_id} on Q{self.question_id} at {self.clicked_at}"