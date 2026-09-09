from django.db import models
from django.urls import reverse
from django.utils import timezone


class Post(models.Model):
    """Travel-guide / SEO article. Body is HTML written in admin."""

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    excerpt = models.TextField(blank=True, help_text="Shown on cards and in meta description")
    body = models.TextField(help_text="HTML")
    cover_url = models.URLField(blank=True)
    # Optional link to a destination so the article can cross-sell its plans.
    country = models.ForeignKey("catalog.Country", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="posts")
    region = models.ForeignKey("catalog.Region", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="posts")
    seo_title = models.CharField(max_length=140, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"slug": self.slug})
