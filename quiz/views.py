import random
from django.db.models import Prefetch, Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.http import HttpResponseBadRequest
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

from .models import Quiz, Round, Question, AnswerOption, Attempt, Answer, PHASE_WAITING, PHASE_ANSWER, PHASE_REVEAL, PHASE_FINISHED, AVATARS

ADJECTIVES = [
    "Spooky", "Creepy", "Wicked", "Ghostly", "Haunted", "Mysterious", "Eerie",
    "Sinister", "Ghoulish", "Shadowy", "Cursed", "Bloody", "Frightful",
    "Moonlit", "Twisted", "Dark", "Pumpkin", "Bony", "Phantom", "Howling"
]

ANIMALS = [
    "Bat", "Cat", "Crow", "Raven", "Owl", "Spider", "Toad", "Rat", "Wolf",
    "Goblin", "Vampire", "Zombie", "Witch", "Mummy", "Skeleton", "Ghost",
    "Pumpkin", "Werewolf", "Demon", "Reaper"
]

def generate_silly_name():
    return f"{random.choice(ADJECTIVES)} {random.choice(ANIMALS)}"

def home(request):
    # Last 10 finished quizzes, most recent first
    quizzes = (
        Quiz.objects.filter(phase=PHASE_FINISHED)
        .order_by('-finished_at', '-created_at')[:10]
        .prefetch_related(
            Prefetch('attempts', queryset=Attempt.objects.order_by('-score', 'started_at'))
        )
    )

    recent = []
    for q in quizzes:
        attempts = list(q.attempts.all())
        if attempts:
            top_score = attempts[0].score
            winners = [a for a in attempts if a.score == top_score]
        else:
            top_score = 0
            winners = []
        recent.append({
            "quiz": q,
            "winners": winners,
            "top_score": top_score,
        })

    return render(request, "quiz/home.html", {"recent": recent, "version": settings.VERSION})

def join_by_code(request):
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        name = (request.POST.get("name") or "").strip()
        avatar = (request.POST.get("avatar") or "").strip()
        quiz = Quiz.objects.filter(access_code=code, is_active=True).first()
        if not quiz:
            return render(request, "quiz/join.html", {
                "error": "Invalid or inactive code.",
                "code": code, "name": name, "avatars": AVATARS, "suggested": generate_silly_name(),
            })
        with transaction.atomic():
            attempt, created = Attempt.objects.get_or_create(quiz=quiz, name=name or "")
            if avatar and attempt.avatar != avatar:
                attempt.avatar = avatar
                attempt.save(update_fields=["avatar"])
        return redirect("quiz:lobby", attempt_id=attempt.id)

    # GET → show join form with suggested name and avatar choices
    return render(request, "quiz/join.html", {
        "suggested": generate_silly_name(),
        "avatars": AVATARS,
    })

@never_cache
def frag_silly_name(request):
    # Returns just an <input> pre-filled so HTMX can swap it in-place
    return render(request, "quiz/_silly_name_input.html", {"suggested": generate_silly_name()})

@never_cache
def frag_lobby(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("quiz"), id=attempt_id)
    quiz = attempt.quiz
    quiz.maybe_tick()

    rounds_qs = (
        Round.objects
        .filter(quiz=quiz)
        .annotate(question_count=Count("questions"))
        .order_by("order", "id")
    )

    unassigned_count = Question.objects.filter(quiz=quiz, round__isnull=True).count()
    total_questions = Question.objects.filter(quiz=quiz).count()

    round_summaries = list(rounds_qs)
    if unassigned_count:
        class _Bucket:
            id = None
            name = "Unassigned"
            description = ""
            image = None
            question_count = unassigned_count
        round_summaries.append(_Bucket())

    # If host has started, force-redirect into the game
    if quiz.phase != PHASE_WAITING:
        url = reverse("quiz:play", args=[attempt.id])
        return HttpResponse(f'<script>window.location.href="{url}";</script>')

    # Always build a fresh player list
    return render(
        request,
        "quiz/_lobby_fragment.html",
        {"quiz": quiz, "round_summaries": round_summaries, "total_questions": total_questions,} 
    )

def lobby(request, attempt_id):
    """Full lobby page — static shell around the live-updating fragment."""
    attempt = get_object_or_404(Attempt.objects.select_related("quiz"), id=attempt_id)
    quiz = attempt.quiz
    rounds_qs = (
        Round.objects
        .filter(quiz=quiz)
        .annotate(question_count=Count("questions"))
        .order_by("order", "id")
    )

    unassigned_count = Question.objects.filter(quiz=quiz, round__isnull=True).count()
    total_questions = Question.objects.filter(quiz=quiz).count()

    round_summaries = list(rounds_qs)
    if unassigned_count:
        class _Bucket:
            id = None
            name = "Unassigned"
            description = ""
            image = None
            question_count = unassigned_count
        round_summaries.append(_Bucket())
    return render(request, "quiz/lobby.html", {"quiz": quiz, "attempt": attempt, "round_summaries": round_summaries, "total_questions": total_questions,})

def play(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("quiz"), id=attempt_id)
    quiz = attempt.quiz
    quiz.maybe_tick()
    if quiz.phase == PHASE_WAITING:
        return redirect("quiz:lobby", attempt_id=attempt.id)
    return render(request, "quiz/play.html", {"attempt": attempt, "quiz": quiz})

def frag_play(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("quiz"), id=attempt_id)
    quiz = attempt.quiz
    quiz.maybe_tick()
    q = quiz.current_question()
    total = quiz.question_count()

    # --- Handle answer submission (auto-post on click) ---
    if request.method == "POST":
        if quiz.phase != PHASE_ANSWER:
            return HttpResponseBadRequest("Not accepting answers now.")
        # lock after first answer
        existing = Answer.objects.filter(attempt=attempt, question=q).first()
        if not existing:
            option_id = request.POST.get("option")
            try:
                opt = q.options.get(id=option_id)
            except (AnswerOption.DoesNotExist, ValueError, TypeError):
                return HttpResponseBadRequest("Invalid option.")
            Answer.objects.create(attempt=attempt, question=q, selected_option=opt)
        # fall through to render updated panel

    ctx = {"attempt": attempt, "quiz": quiz, "q": q, "idx": quiz.current_index, "total": total,
           "remaining": quiz.phase_remaining()}

    if quiz.phase == PHASE_ANSWER:
        current_answer = Answer.objects.filter(attempt=attempt, question=q).first()
        ctx["current_answer"] = current_answer
        template = "quiz/_play_answer.html"

    elif quiz.phase == PHASE_REVEAL:
        correct_opt = q.options.filter(is_correct=True).first()
        answers = Answer.objects.filter(question=q, attempt__quiz=quiz).select_related("attempt","selected_option")
        right = [a.attempt.name or f"Player {a.attempt_id}" for a in answers if a.selected_option_id == correct_opt.id]
        wrong = [a.attempt.name or f"Player {a.attempt_id}" for a in answers if a.selected_option_id != correct_opt.id]
        ctx.update({"correct_opt": correct_opt, "right": right, "wrong": wrong})
        template = "quiz/_play_reveal.html"

    elif quiz.phase == PHASE_FINISHED:
        attempts = list(Attempt.objects.filter(quiz=quiz).order_by("-score", "started_at"))
        top_score = attempts[0].score if attempts else 0
        winners = [a for a in attempts if a.score == top_score] if attempts else []

        # Build leaderboard with % correct (based on questions answered)
        leaderboard = []
        for a in attempts:
            answered = Answer.objects.filter(attempt=a).count()
            correct = Answer.objects.filter(attempt=a, selected_option__is_correct=True).count()
            pct = round((correct / answered) * 100) if answered else 0
            leaderboard.append({"attempt": a, "answered": answered, "correct": correct, "pct": pct})

        ctx.update({"winners": winners, "top_score": top_score, "leaderboard": leaderboard})
        template = "quiz/_play_finished.html"

    else:
        template = "quiz/_play_waiting.html"

    return render(request, template, ctx)