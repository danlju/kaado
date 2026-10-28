from django.contrib.auth import get_user_model
def ensure_default_user():
    user, _ = get_user_model().objects.get_or_create(username="default")
    return user
