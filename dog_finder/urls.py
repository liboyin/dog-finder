"""Public routes available during scaffolding."""

from django.urls import path

from dog_finder import views
from dog_finder.subscriptions import views as subscriptions

urlpatterns = [
    path("search/new/", subscriptions.create, name="search-create"),
    path("search/requested/", subscriptions.requested, name="search-requested"),
    path("s/confirm/<str:token>/", subscriptions.confirm, name="search-confirm"),
    path("s/manage/<str:token>/", subscriptions.manage, name="search-manage"),
    path("s/cancel/<str:token>/", subscriptions.cancel, name="search-cancel"),
    path("s/edit/<str:token>/", subscriptions.edit, name="search-edit"),
    path("s/renew/<str:token>/", subscriptions.renew, name="search-renew"),
    path("s/unsubscribe/<str:token>/", subscriptions.unsubscribe, name="search-unsubscribe"),
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
]
