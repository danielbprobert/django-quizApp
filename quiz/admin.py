from django.contrib import admin, messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import (
    Quiz,
    Question,
    AnswerOption,
    Attempt,
    Answer,
    PHASE_ANSWER,
    PHASE_WAITING
)
from .utils import broadcast_quiz


@admin.action(description="Start selected quiz")
def start_quiz(modeladmin, request, queryset):
    """
    Starts the selected quizzes at question index 0, enters ANSWER phase,
    timestamps the start, and broadcasts the phase change so clients update instantly.
    """
    started = 0
    skipped = 0

    for quiz in queryset:
        if quiz.questions.count() == 0:
            skipped += 1
            messages.warning(
                request,
                f"Quiz '{quiz.title}' has no questions – not started."
            )
            continue

        quiz.phase = PHASE_ANSWER
        quiz.current_index = 0
        quiz.phase_started_at = timezone.now()
        quiz.started_at = quiz.started_at or timezone.now()
        quiz.save(update_fields=["phase", "current_index", "phase_started_at", "started_at"])

        # Notify connected clients (lobby & play pages) to refresh immediately.
        broadcast_quiz(
            quiz.id,
            {"kind": "phase", "phase": quiz.phase, "idx": quiz.current_index}
        )
        started += 1

    if started:
        messages.success(request, f"Started {started} quiz(es).")
    if not started and skipped == 0:
        messages.info(request, "No quizzes were started.")

@admin.action(description="Reset selected quiz")
def reset_quiz(modeladmin, request, queryset):
    """
    Resets quizzes to WAITING phase without deleting attempts or answers.
    Use this if something gets stuck. You can clear attempts in the Attempt list if desired.
    """
    reset = 0
    for quiz in queryset:
        quiz.phase = PHASE_WAITING
        quiz.current_index = 0
        quiz.phase_started_at = None
        quiz.started_at = None
        quiz.finished_at = None
        quiz.save(update_fields=["phase", "current_index", "phase_started_at", "started_at", "finished_at"])

        try:
            broadcast_quiz(quiz.id, {"kind": "phase", "phase": quiz.phase, "idx": quiz.current_index})
        except Exception:
            pass

        reset += 1

    if reset:
        messages.success(request, f"Reset {reset} quiz(es) to WAITING.")
    else:
        messages.info(request, "No quizzes were reset.")

class FourOptionsOneCorrectFormset(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)

        # Lock the order field in the UI if it exists
        if 'order' in form.fields:
            form.fields['order'].disabled = True

        # Only set initial order for real inline rows, not the empty template
        if index is not None and not form.instance.pk:
            form.initial.setdefault('order', index + 1)

    def clean(self):
        super().clean()
        count = 0
        correct = 0
        orders = set()

        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                count += 1
                if form.cleaned_data.get("is_correct"):
                    correct += 1

                # read order from cleaned_data or fallback to initial (since field is disabled / readonly)
                order = form.cleaned_data.get("order") or form.initial.get("order")

        if count != 4:
            raise ValidationError("Each question must have exactly 4 options.")
        if correct != 1:
            raise ValidationError("Exactly one option must be marked correct.")

    def save_new(self, form, commit=True):
        obj = super().save_new(form, commit=False)
        # persist the order even if the field was disabled/read-only
        obj.order = form.cleaned_data.get("order") or form.initial.get("order")
        if commit:
            obj.save()
        return obj



class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 4
    max_num = 4
    min_num = 4
    formset = FourOptionsOneCorrectFormset
    fields = ("order", "text", "image", "is_correct")
    readonly_fields = ("order",)
    def get_queryset(self, request):
        # keep them listed in order
        qs = super().get_queryset(request)
        return qs.order_by("order")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "order")
    list_filter = ("quiz",)
    inlines = [AnswerOptionInline]
    fields = ("quiz", "order", "text", "image", "explanation")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "access_code", "is_active", "phase", "current_index", "created_at")
    readonly_fields = ("access_code", "phase", "current_index", "phase_started_at", "started_at", "finished_at")
    search_fields = ("title", "access_code")
    actions = [start_quiz, reset_quiz]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "name", "score", "started_at", "finished_at")
    list_filter = ("quiz",)


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option")
