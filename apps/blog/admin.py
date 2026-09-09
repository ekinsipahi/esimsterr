from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "published_at", "country", "region")
    list_filter = ("is_published", "published_at")
    search_fields = ("title", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
    list_editable = ("is_published",)
    autocomplete_fields = ("country", "region")
    date_hierarchy = "published_at"
