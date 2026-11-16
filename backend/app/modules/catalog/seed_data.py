"""Starter catalog. Edit freely; `make seed` upserts these rows by their fixed IDs.

Topic names match the Figma chips (the UI is Indonesian); descriptions steer generation.
"Acak" in Figma is the random topic mode, not a topic row.
Persona voice keys are provider-neutral placeholders until a TTS model is chosen; the
TTS adapter will map them to real voices.
"""

from uuid import UUID, uuid5

_NAMESPACE = UUID("6f1c2b9e-7a43-4f0e-9d55-3c1e2a8b4d10")


def stable_id(kind: str, slug: str) -> UUID:
    return uuid5(_NAMESPACE, f"{kind}:{slug}")


TOPICS = [
    ("school", "Sekolah", "School life: classes, teachers, friends, school events."),
    ("sports", "Olahraga", "Sports, exercise, matches and healthy activity."),
    ("technology", "Teknologi", "Phones, the internet, apps and everyday technology."),
    ("culture", "Budaya", "Indonesian and world culture, festivals and traditions."),
    ("nature", "Alam", "Nature, animals, weather and the environment."),
    ("travel", "Perjalanan", "Trips, transport, holidays and visiting new places."),
    ("food", "Makanan", "Food, cooking, restaurants and favourite dishes."),
    ("daily-life", "Kehidupan Sehari-hari", "Family, home, hobbies and daily routines."),
]

PERSONAS = [
    (
        "classmate",
        "Friendly Classmate",
        "A friendly classmate chatting about everyday life.",
        "Speak casually and warmly. Ask one short follow-up question per turn about the "
        "student's day, weekend, hobbies or plans. Keep replies to one or two sentences.",
        "female_1",
    ),
    (
        "teacher",
        "English Teacher",
        "A patient English teacher having a practice conversation.",
        "Be encouraging and clear. Ask open questions that invite longer answers. "
        "Do not correct mistakes during the conversation; feedback comes afterwards.",
        "male_1",
    ),
    (
        "airport-officer",
        "Airport Officer",
        "An airport check-in officer helping a traveller.",
        "Play a polite check-in officer. Ask about the destination, passport, luggage and "
        "seat preference, one question at a time. Stay in the airport scenario.",
        "female_2",
    ),
    (
        "shop-assistant",
        "Shop Assistant",
        "A shop assistant helping a customer find and buy something.",
        "Play a helpful shop assistant. Ask what the customer needs, offer options, talk "
        "about sizes and prices in rupiah, and complete the purchase.",
        "male_2",
    ),
    (
        "tour-guide",
        "Tour Guide",
        "A tour guide showing a visitor around a city in Indonesia.",
        "Play an enthusiastic local guide. Describe places briefly and ask the visitor "
        "what they would like to see, eat or do next.",
        "female_1",
    ),
]
