from django.contrib import admin, messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import (
    Quiz,
    Round,
    Question,
    AnswerOption,
    Attempt,
    Answer,
    PHASE_ANSWER,
    PHASE_WAITING,
    SpecialClick,   # NEW
)
from .utils import broadcast_quiz


@admin.action(description="Start selected quiz")
def start_quiz(modeladmin, request, queryset):
    started = 0
    skipped = 0
    for quiz in queryset:
        if quiz.questions.count() == 0:
            skipped += 1
            messages.warning(request, f"Quiz '{quiz.title}' has no questions – not started.")
            continue

        quiz.phase = PHASE_ANSWER
        quiz.current_index = 0
        quiz.phase_started_at = timezone.now()
        quiz.started_at = quiz.started_at or timezone.now()
        quiz.save(update_fields=["phase", "current_index", "phase_started_at", "started_at"])

        broadcast_quiz(quiz.id, {"kind": "phase", "phase": quiz.phase, "idx": quiz.current_index})
        started += 1

    if started:
        messages.success(request, f"Started {started} quiz(es).")
    if not started and skipped == 0:
        messages.info(request, "No quizzes were started.")


@admin.action(description="Reset selected quiz")
def reset_quiz(modeladmin, request, queryset):
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
        if 'order' in form.fields:
            form.fields['order'].disabled = True
        if index is not None and not form.instance.pk:
            form.initial.setdefault('order', index + 1)

    def clean(self):
        super().clean()
        count = 0
        correct = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                count += 1
                if form.cleaned_data.get("is_correct"):
                    correct += 1
        if count != 4:
            raise ValidationError("Each question must have exactly 4 options.")
        if correct != 1:
            raise ValidationError("Exactly one option must be marked correct.")

    def save_new(self, form, commit=True):
        obj = super().save_new(form, commit=False)
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
        qs = super().get_queryset(request)
        return qs.order_by("order")


# --- Round inline under Quiz ---
class RoundInline(admin.StackedInline):
    model = Round
    extra = 0
    fields = ("order", "name", "description", "image", "pause_seconds")  # UPDATED
    ordering = ("order", "id")
    show_change_link = True


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "round", "order", "has_special_icon")  # UPDATED
    list_filter = ("quiz", "round", "has_special_icon")                  # UPDATED
    inlines = [AnswerOptionInline]
    fields = (
        "quiz",
        "round",
        "order",
        "text",
        "image",
        "explanation",
        "answer_seconds",
        "reveal_seconds",
        "has_special_icon",   # NEW
        "special_icon",       # NEW
    )

    # Limit the "round" choices to rounds belonging to the selected quiz
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        from django.forms import ModelChoiceField

        # default to no filtering
        qs = Round.objects.all()

        if obj and obj.quiz_id:
            qs = qs.filter(quiz=obj.quiz_id)
        else:
            # When adding, try to read the selected quiz from GET/POST
            quiz_id = request.GET.get("quiz") or request.POST.get("quiz")
            if quiz_id:
                qs = qs.filter(quiz_id=quiz_id)

        if "round" in form.base_fields:
            form.base_fields["round"] = ModelChoiceField(
                queryset=qs, required=False, empty_label="— No round —"
            )
        return form


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "access_code", "is_active", "phase", "current_index", "created_at")
    readonly_fields = ("access_code", "phase", "current_index", "phase_started_at", "started_at", "finished_at")
    search_fields = ("title", "access_code")
    actions = [start_quiz, reset_quiz]
    inlines = [RoundInline]   # create/manage rounds directly under a quiz


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("name", "quiz", "order", "pause_seconds")  # UPDATED
    list_filter = ("quiz",)
    search_fields = ("name",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "name", "score", "started_at", "finished_at")
    list_filter = ("quiz",)


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option")

# --- Custom filter to show only questions that have special icons ---
class SpecialQuestionFilter(admin.SimpleListFilter):
    title = "Question (special only)"
    parameter_name = "question"

    def lookups(self, request, model_admin):
        qs = (
            Question.objects
            .filter(has_special_icon=True)
            .order_by("quiz__title", "order")
        )
        return [(q.id, f"{q.quiz.title} – Q{q.id}") for q in qs]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(question_id=value)
        return queryset



@admin.register(SpecialClick)
class SpecialClickAdmin(admin.ModelAdmin):
    list_display = ("quiz", "question", "player_name", "attempt", "clicked_at_full")
    list_filter = ("quiz", SpecialQuestionFilter)
    search_fields = ("attempt__name", "quiz__title")
    date_hierarchy = "clicked_at"

    def player_name(self, obj):
        if obj.attempt.name:
            return obj.attempt.name
        return f"Player {obj.attempt_id}"
    player_name.short_description = "Player"

    def clicked_at_full(self, obj):
        # Force full timestamp including seconds
        return obj.clicked_at.strftime("%Y-%m-%d %H:%M:%S")
    clicked_at_full.short_description = "Clicked at"
    clicked_at_full.admin_order_field = "clicked_at"