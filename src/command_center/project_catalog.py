"""Fixed project catalog; entries describe boundaries, never credentials or grants."""

PROJECTS = (
    {'id': 'command-center', 'label': 'AI Commander', 'risk': 'platform',
     'boundary': 'Управляющий контур; production deployment требует отдельного разрешения.'},
    {'id': 'vanilla-sugar', 'label': 'Ваниль и Сахар', 'risk': 'business_data',
     'boundary': 'Самостоятельная CRM; клиентские данные и production не переносятся в Commander.'},
    {'id': 'lnauto', 'label': 'LNAuto', 'risk': 'paused',
     'boundary': 'Проект на паузе; подключение само по себе не возобновляет разработку.'},
    {'id': 'capital-lab', 'label': 'Capital Lab', 'risk': 'financial',
     'boundary': 'Аналитика; торговые и финансовые операции запрещены без отдельного разрешения.'},
)

BY_ID = {item['id']: item for item in PROJECTS}
IDS = frozenset(BY_ID)


def summary(project_id):
    return dict(BY_ID[project_id])
