from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('loans/', views.loan_list, name='loan_list'),
    path('loans/apply/<int:loan_type_id>/', views.loan_apply, name='loan_apply'),
    path('loans/<int:application_id>/', views.loan_detail, name='loan_detail'),
    path('loans/<int:application_id>/withdraw/', views.loan_withdraw, name='loan_withdraw'),
    path('loans/<int:application_id>/payment/', views.make_payment, name='make_payment'),
    path('loans/<int:application_id>/payments/', views.payment_history, name='payment_history'),
    path('profile/', views.profile, name='profile'),
    path('profile/update/', views.profile_update, name='profile_update'),
    path('applications/', views.application_history, name='application_history'),
    path('notifications/', views.notifications, name='notifications'),
]