"""
Custom JWT authentication serializers and views
"""
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import serializers


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that accepts email instead of username
    """
    username_field = User.EMAIL_FIELD

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field] = serializers.EmailField()
        self.fields.pop('username', None)

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        password = attrs.get('password')

        if email and password:
            try:
                # Use filter().first() to handle duplicate emails gracefully
                user = User.objects.filter(email=email).first()
                
                if not user:
                    raise serializers.ValidationError(
                        'No active account found with the given credentials'
                    )
                
                user = authenticate(username=user.username, password=password)

                if user is None:
                    raise serializers.ValidationError(
                        'No active account found with the given credentials'
                    )

                refresh = self.get_token(user)
                return {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }

            except User.MultipleObjectsReturned:
                # Multiple users with same email - should not happen but handle it
                raise serializers.ValidationError(
                    'Multiple accounts found. Please contact support.'
                )

        raise serializers.ValidationError('Must include "email" and "password".')


class EmailTokenObtainPairView(TokenObtainPairView):
    """Token view that accepts email instead of username"""
    serializer_class = EmailTokenObtainPairSerializer
