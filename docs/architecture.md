# Architecture d’Enetari

## Mode hors ligne sur le K1

```text
Micro
  → Whisper.cpp
  → mémoire SQLite
  → llama-server + Qwen3 4B
  → Piper
  → haut-parleur
```

Le modèle Qwen reste chargé en mémoire grâce à `llama-server`. L’application Enetari communique avec lui via une API locale sur `127.0.0.1:8080`.

## Objectifs d’architecture

- Chaque moteur doit pouvoir être remplacé indépendamment.
- La personnalité et la mémoire ne doivent pas dépendre du modèle LLM choisi.
- La branche `main` doit toujours être réinstallable sur une machine vierge.
- Les modèles et les données locales ne sont pas versionnés dans Git.
- Les services système sont générés par l’installateur.

## Évolutions prévues

- démarrage automatique de l’application Enetari ;
- conversation vocale continue ;
- identification volontaire des utilisateurs ;
- analyse d’intention ;
- bascule automatique entre le K1 local et le serveur principal ;
- mémoire plus riche et contrôlée.
