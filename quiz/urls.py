from django.urls import path
from . import views

app_name = "quiz"
urlpatterns = [
    path("", views.home, name="home"),
    path("join/", views.join_by_code, name="join"),
    path("lobby/<int:attempt_id>/", views.lobby, name="lobby"),
    path("play/<int:attempt_id>/", views.play, name="play"),

    path("frag/lobby/<int:attempt_id>/", views.frag_lobby, name="frag_lobby"),
    path("frag/play/<int:attempt_id>/", views.frag_play, name="frag_play"),
    path("frag/silly-name/", views.frag_silly_name, name="frag_silly_name"),

    # NEW: special prize icon click
    path(
        "frag/special-click/<int:attempt_id>/<int:question_id>/",
        views.special_click,
        name="special_click",
    ),
]
