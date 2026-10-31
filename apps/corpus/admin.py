from django.contrib import admin

from .models import Chunk, Document, Source

admin.site.register([Source, Document])


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("chunk_id", "document", "ordinal", "page_start")
    exclude = ("embedding",)
