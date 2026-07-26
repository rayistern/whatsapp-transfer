"""Conversion layer: iOS ChatStorage.sqlite -> Android msgstore.db.

This package transforms the platform-neutral Corpus (populated by
wat.extract from iOS data) into a modern Android WhatsApp database.

Sub-modules:
- android_schema: DDL and creation of the empty Android msgstore.db.
- mappings: Constants and functions for iOS -> Android field translation
  (timestamps, message types, status codes).
- media: iOS -> Android media path remapping (naming conventions, folder
  structure, MIME type resolution).
- writer: Orchestrates the actual INSERT logic, populating all Android
  tables from a Corpus.

The conversion is deliberately one-directional (iOS -> Android). The
architecture was chosen during Phase 0 (April 2025) to match the
most common WhatsApp migration direction (iPhone -> Android).
"""
