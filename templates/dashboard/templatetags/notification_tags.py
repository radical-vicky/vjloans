from django import template
from ..models import Notification

register = template.Library()

@register.simple_tag
def get_unread_notification_count(user):
    if user.is_authenticated:
        return Notification.objects.filter(user=user, is_read=False).count()
    return 0