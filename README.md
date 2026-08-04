# Enetari

Enetari est une assistante vocale personnelle conçue pour fonctionner localement sur un mini-PC, avec un mode hors ligne complet.

## Structure du dépôt

```text
Enetari/
├── app/
├── install/
├── services/
├── config/
├── tests/
├── docs/
├── scripts/
├── README.md
├── CHANGELOG.md
└── .gitignore
```

## Installation sur le K1

Depuis la racine du dépôt :

```bash
sudo python3 install/install_enetari.py
```

L’installateur met en place :

- Whisper.cpp pour la reconnaissance vocale locale ;
- Piper pour la synthèse vocale locale ;
- llama.cpp avec Vulkan ;
- Qwen3 4B au format GGUF ;
- SQLite pour la mémoire ;
- la personnalité protégée ;
- `llama-server`, chargé automatiquement au démarrage ;
- le lanceur `enetari`.

## Vérification

```bash
systemctl status enetari-llm --no-pager
curl http://127.0.0.1:8080/health
enetari --text "Comment vas-tu ?" --no-voice
```

## Emplacements installés

```text
/opt/enetari
/etc/enetari
/var/lib/enetari
/usr/local/bin/enetari
/etc/systemd/system/enetari-llm.service
```

## Règle du projet

La branche `main` doit rester installable sur une machine Ubuntu compatible avec une seule commande d’installation.
