"""Public routes available during scaffolding."""

from django.urls import path

from dog_finder import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
]
