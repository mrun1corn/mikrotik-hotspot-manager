# mikrotik-hotspot-manager
# MikroTik Hotspot Management & Telegram Bot

A PHP-based hotspot login/status portal integrated with MikroTik RouterOS API, alongside a Telegram bot for hotspot user approval and management.

---

## Features

- User login and session status display (upload, download, uptime, remaining time)
- Buy packages integration (via payment page)
- Logout functionality
- Telegram bot to approve hotspot users, list active users, and check usage
- Clean, responsive UI

---

## Requirements

- PHP 7.4+ with Composer
- MikroTik RouterOS with API enabled
- Telegram Bot API token and Admin Chat ID
- Web server (Apache, Nginx, etc.) with HTTPS recommended

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/mikrotik-hotspot.git
cd mikrotik-hotspot

