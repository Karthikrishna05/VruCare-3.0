from django.contrib import admin

from .models import Citation, Conversation, ExternalArticle, Message

admin.site.register([Citation, Conversation, ExternalArticle, Message])
