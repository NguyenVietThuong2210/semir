"""
App/models/shop.py

Shop name normalization:
  ShopNameTitle  — canonical display name (e.g. "Bala VN Hanoi Aeon Mall - Direct")
  ShopNameAlias  — raw variant names that map to a title
                   (e.g. "巴拉越南河内市HA DONG AEON MALL-直营店", "Bala Hanoi Aeon Mall", …)

All analytics group by title_id and display title.
"""
from django.db import models


class ShopNameTitle(models.Model):
    title = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Shop Name Title"
        verbose_name_plural = "Shop Name Titles"

    def __str__(self):
        return self.title


class ShopNameAlias(models.Model):
    title = models.ForeignKey(
        ShopNameTitle,
        on_delete=models.CASCADE,
        related_name="aliases",
    )
    alias = models.CharField(max_length=1000, unique=True)

    class Meta:
        ordering = ["alias"]
        verbose_name = "Shop Name Alias"
        verbose_name_plural = "Shop Name Aliases"

    def __str__(self):
        return f"{self.alias} → {self.title.title}"
