# Installation

## Pré-requis

- Ubuntu Server compatible ;
- connexion Internet pour la première installation ;
- accès `sudo` ;
- espace disque suffisant pour les modèles.

## Installation complète

```bash
git clone https://github.com/shinn55/Enetari.git
cd Enetari
sudo python3 install/install_enetari.py
```

## Vérification du LLM local

```bash
systemctl status enetari-llm --no-pager
curl http://127.0.0.1:8080/health
```

## Test texte

```bash
enetari --text "Comment vas-tu ?" --no-voice
```

## Test vocal

```bash
enetari
```

Une fois l’installation terminée, les conversations locales ne nécessitent plus Internet.
