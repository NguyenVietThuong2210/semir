from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


@csrf_protect
@never_cache
def login_view(request):
    """
    Secure login view with ASVS Level 1 compliance
    - V2.1: Password security
    - V3.1: Session management
    - V4.1: Access control
    """
    if request.user.is_authenticated:
        return redirect('analytics_dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                login(request, user)
                logger.info(f'User {username} logged in successfully')

                # Regenerate session key for security
                request.session.cycle_key()

                next_url = request.GET.get('next', 'analytics_dashboard')
                return redirect(next_url)
            else:
                logger.warning(f'Failed login attempt for username: {username}')
                messages.error(request, 'Invalid username or password')
        else:
            messages.error(request, 'Invalid username or password')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})


@csrf_protect
def logout_view(request):
    """Secure logout with session cleanup"""
    if request.method == 'POST':
        username = request.user.username if request.user.is_authenticated else 'Anonymous'
        logout(request)
        logger.info(f'User {username} logged out')
        return redirect('login')
    return redirect('analytics_dashboard')


@csrf_protect
@never_cache
@login_required
def register_view(request):
    """
    User registration - requires login and manage_users permission.
    Only admins can create new accounts.
    """
    from App.permissions import user_has_perm
    if not user_has_perm(request.user, 'manage_users'):
        messages.error(request, 'You do not have permission to register new users.')
        return redirect('home')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            logger.info(f'New user registered: {username}')

            # Auto-assign viewer role to new user
            from App.models import Role, UserProfile
            try:
                viewer_role = Role.objects.get(name='viewer')
                UserProfile.objects.create(user=user, role=viewer_role)
            except Exception:
                pass

            messages.success(request, f'Account created for {username}.')
            return redirect('user_management')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = UserCreationForm()

    return render(request, 'register.html', {'form': form})
