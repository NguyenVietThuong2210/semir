"""App/views/home.py — Home and static pages."""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from App.permissions import requires_perm


@login_required
def home(request):
    """Home page view."""
    return render(request, "home.html")


@requires_perm("page_formulas")
def formulas_page(request):
    """Display formulas and definitions used in analytics."""
    return render(request, "formulas.html")
