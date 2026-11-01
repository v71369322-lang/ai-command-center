# Mobile/project release checkpoint — 1 ноября 2026

Application target `c3619ea0b94efcc0f0acae462bebefd3c4808eea` объединяет изменения после
runtime checkpoint `322186dc180257c618d8b159c78faa6e5bbf0b43`: центр внимания,
напоминания, календарные черновики, голосовые поручения, status компонентов,
project connection registry и bounded repair preparation.

`scripts/project_release_checkpoint.py` проверяет офлайн, что target является
потомком checkpoint, необходимые модули присутствуют, а модели БД, lockfiles,
Dockerfiles, compose и web lockfile не изменились. Он не читает credentials, не
обращается к VPS/GitHub/OpenAI и не начинает deployment.

## Что уже доказано

- Telegram voice/system PR #71: финальный CI SUCCESS.
- Project control PR #72: targeted Python 130 passed, дополнительный readiness
  scope 64 passed, web production build passed; финальный CI должен соответствовать
  target SHA выше.
- Новый API закреплён в `contracts/openapi.json`.

## Что намеренно осталось до компьютера

1. Read-only сверить фактический live bundle и временное Telegram memory containment.
2. Подготовить отдельный exact operator profile для перехода с подтверждённого
   predecessor на target; старые release names не переназначать.
3. Собрать target images на обоих rootless daemons и проверить revision labels.
4. Stage candidate без активации, сверить bundle/connection digests.
5. Получить отдельное точное разрешение на apply и выполнить postcheck Telegram,
   worker, broker, watchdog, API и БД.
6. Только после стабильного релиза выбрать один пилотный repository и выполнить
   read-only GitHub connection evidence.

Пока эти пункты не выполнены, package остаётся `OFFLINE_RELEASE_CHECKPOINT`.
Автоматический retry, deployment и подключение проектов запрещены.
