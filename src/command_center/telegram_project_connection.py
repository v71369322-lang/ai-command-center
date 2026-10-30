"""Fixed connection blueprints in Telegram; no probing or connection activation."""
from .project_connections import connection_plan
from .project_inbox import PROJECTS


def reply(project_id):
    if project_id is None:
        choices = '\n'.join(f'{label}: /connection {key}' for key, label in PROJECTS)
        return ('Планы подключения проектов. Отправьте команду целиком с ID проекта:\n' + choices + '\n\n'
                'План показывает ожидаемый репозиторий, среду проверки и доставку на сервер. '
                'Подключения здесь ещё не проверялись. Просмотр не запускает задачи и не разрешает расходы.')
    plan = connection_plan('owner', project_id)
    label = dict(PROJECTS)[plan['project_id']]
    return (f'План подключения: {label}.\n'
            f'Ожидаемый репозиторий: {plan["expected_repository"]}.\n\n'
            '1. Репозиторий — не проверено. Проверить доступ к нужному репозиторию '
            'и согласовать разрешённые операции.\n'
            '2. Среда проверки — не проверено. Подготовить изолированную сборку и тесты без рабочих данных.\n'
            '3. Доставка на сервер — не проверено. Настроить установку разрешённой версии '
            'и проверку после обновления.\n\n'
            'Это план подключения; доступы, среда и сервер этой командой не проверяются. '
            'Просмотр не подключает проект, не запускает задачи и не разрешает расходы.\n'
            f'Запросы проекта: /requests {project_id}. Все проекты: /projects.')
