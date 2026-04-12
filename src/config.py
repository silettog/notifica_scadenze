import os

# Helper per leggere booleani in modo sicuro
def get_bool_input(name, default=False):
    val = os.environ.get(name, str(default)).lower()
    return val in ['true', '1', 'yes', 'y']

# Variabili GITHUB standard
repository_owner = os.environ.get('GITHUB_REPOSITORY_OWNER')
repository = os.environ.get('GITHUB_REPOSITORY', '/')
repository_name = repository.split('/')[1] if '/' in repository else ''
server_url = os.environ.get('GITHUB_SERVER_URL')
api_endpoint = os.environ.get('GITHUB_GRAPHQL_URL')

# Input della Action
repository_owner_type = os.environ.get('INPUT_REPOSITORY_OWNER_TYPE')
is_enterprise = get_bool_input('INPUT_ENTERPRISE_GITHUB')
dry_run = get_bool_input('INPUT_DRY_RUN')
gh_token = os.environ.get('INPUT_GH_TOKEN')

# Gestione sicura del numero progetto
try:
    project_number = int(os.environ.get('INPUT_PROJECT_NUMBER', 0))
except ValueError:
    raise Exception("INPUT_PROJECT_NUMBER deve essere un numero valido")

duedate_field_name = os.environ.get('INPUT_DUEDATE_FIELD_NAME')
notification_type = os.environ.get('INPUT_NOTIFICATION_TYPE')
notify_for = os.environ.get('INPUT_NOTIFY_FOR')

# Validazione
if notification_type not in ['comment', 'email']:
    raise Exception(f'Unsupported notification type: {notification_type}')

if notify_for not in ['expiring_issues', 'missing_duedate']:
    raise Exception(f'Unsupported notify_for value: {notify_for}') # Corretto qui

# Inizializzazione variabili opzionali per evitare NameError
task_status_field_name = os.getenv('INPUT_TASK_STATUS_FIELD_NAME', 'Status')
excluded_statuses = os.getenv('INPUT_EXCLUDED_STATUSES', '')

if notification_type == 'email':
    smtp_server = os.environ.get('INPUT_SMTP_SERVER')
    smtp_port = os.environ.get('INPUT_SMTP_PORT')
    smtp_username = os.environ.get('INPUT_SMTP_USERNAME')
    smtp_password = os.environ.get('INPUT_SMTP_PASSWORD')
    smtp_from_email = os.environ.get('INPUT_SMTP_FROM_EMAIL')
    mail_aggiuntive = os.environ.get('INPUT_MAIL_AGGIUNTIVE', '')
    
    try:
        giorni_preavviso = int(os.environ.get('INPUT_GIORNI_PREAVVISO', 0))
    except ValueError:
        giorni_preavviso = 0
        
    project_name = os.getenv('INPUT_PROJECT_NAME', 'Default Project')
