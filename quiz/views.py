import random
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.http import HttpResponseBadRequest
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.urls import reverse
from .models import Quiz, Question, AnswerOption, Attempt, Answer, PHASE_WAITING, PHASE_ANSWER, PHASE_REVEAL, PHASE_FINISHED, AVATARS

ADJECTIVES = [
    "Swift","Bouncy","Sneaky","Cheerful","Curious","Zesty","Witty","Brave",
    "Fizzing","Sunny","Cosmic","Nifty","Zippy","Gleeful","Lucky","Mighty"
]
ANIMALS = [
    "Fox","Panda","Frog","Tiger","Monkey","Unicorn","Octopus","Bee",
    "Owl","Koala","Pup","Kitten","Hedgehog","Dino","Penguin","Whale"
]

def generate_silly_name():
    return f"{random.choice(ADJECTIVES)} {random.choice(ANIMALS)}"

def home(request):
    return render(request, "quiz/home.html")

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

    # If host has started, force-redirect into the game
    if quiz.phase != PHASE_WAITING:
        url = reverse("quiz:play", args=[attempt.id])
        return HttpResponse(f'<script>window.location.href="{url}";</script>')

    # Always build a fresh player list
    return render(
        request,
        "quiz/_lobby_fragment.html",
        {"quiz": quiz}  # template uses quiz.attempts.all dynamically
    )

def lobby(request, attempt_id):
    """Full lobby page — static shell around the live-updating fragment."""
    attempt = get_object_or_404(Attempt.objects.select_related("quiz"), id=attempt_id)
    quiz = attempt.quiz
    return render(request, "quiz/lobby.html", {"quiz": quiz, "attempt": attempt})

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