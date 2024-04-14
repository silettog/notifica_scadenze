import os

repository_owner = os.environ['GITHUB_REPOSITORY_OWNER']
repository_owner_type = os.environ['INPUT_REPOSITORY_OWNER_TYPE']
repository = os.environ['GITHUB_REPOSITORY']
repository_name = repository.split('/')[1]
server_url = os.environ['GITHUB_SERVER_URL']
is_enterprise = True if os.environ.get('INPUT_ENTERPRISE_GITHUB') == 'True' else False
dry_run = True if os.environ.get('INPUT_DRY_RUN') == 'True' else False

gh_token = os.environ['INPUT_GH_TOKEN']
project_number = int(os.environ['INPUT_PROJECT_NUMBER'])
api_endpoint = os.environ['GITHUB_GRAPHQL_URL']
duedate_field_name = os.environ['INPUT_DUEDATE_FIELD_NAME']
status_field_name = os.environ['INPUT_TASK_STATUS_FIELD_NAME']
notification_type = os.environ['INPUT_NOTIFICATION_TYPE']
notify_for = os.environ['INPUT_NOTIFY_FOR']

if notification_type not in ['comment', 'email']:
    raise Exception(f'Unsupported notification type {notification_type}')

if notify_for not in ['expiring_issues', 'missing_duedate']:
    raise Exception(f'Unsupported notify_for value {notification_type}')

if notification_type == 'email':
    smtp_server = os.environ['INPUT_SMTP_SERVER']
    smtp_port = os.environ['INPUT_SMTP_PORT']
    smtp_username = os.environ['INPUT_SMTP_USERNAME']
    smtp_password = os.environ['INPUT_SMTP_PASSWORD']
    smtp_from_email = os.environ['INPUT_SMTP_FROM_EMAIL']
    mail_aggiuntive = os.environ['INPUT_MAIL_AGGIUNTIVE']
    giorni_preavviso = int(os.environ['INPUT_GIORNI_PREAVVISO'])
