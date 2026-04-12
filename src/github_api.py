import requests
import config
from logger import logger

def get_repo_issues(owner, repository, duedate_field_name, after=None, issues=None):
    query = """
    query GetRepoIssues($owner: String!, $repo: String!, $duedate: String!, $after: String) {
      repository(owner: $owner, name: $repo) {
        issues(first: 100, after: $after, states: [OPEN]) {
          nodes {
            id
            title
            number
            url
            assignees(first: 10) {
              nodes {
                name
                email
                login
              }
            }
            projectItems(first: 10) {
              nodes {
                project {
                  number
                }
                statusValue: fieldValueByName(name: "Status") {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                  }
                }
                fieldValueByName(name: $duedate) {
                  ... on ProjectV2ItemFieldDateValue {
                    date
                  }
                }
              }
            }
          }
          pageInfo {
            endCursor
            hasNextPage
          }
        }
      }
    }
    """

    variables = {
        'owner': owner,
        'repo': repository,
        'duedate': duedate_field_name,
        'after': after
    }

    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"}
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"Errore connessione API: {e}")
        return issues or []

    if data.get('errors'):
        logger.error(f"Errore GraphQL Repo: {data['errors']}")
        return issues or []

    # Accesso sicuro ai dati nidificati
    res_data = data.get('data', {}).get('repository', {}).get('issues', {})
    nodes = res_data.get('nodes', [])
    pageinfo = res_data.get('pageInfo', {})

    if issues is None:
        issues = []
    
    issues.extend(nodes)

    if pageinfo.get('hasNextPage'):
        return get_repo_issues(owner, repository, duedate_field_name, pageinfo.get('endCursor'), issues)

    return issues


def get_project_issues(owner, owner_type, project_number, duedate_field_name, task_status_field_name, filters=None):
    """
    Versione corretta con gestione sicura delle variabili e delle graffe.
    """
    clean_type = str(owner_type).lower().strip() if owner_type else "organization"
    type_query = "organization" if clean_type == "organization" else "user"

    logger.info(f"Eseguo query GraphQL su tipo: {type_query} per l'owner: {owner}")
    
    # Usiamo le variabili GraphQL ($statusField e $duedate) invece di interpolare stringhe
    query = f"""
    query($owner: String!, $number: Int!, $duedate: String!, $statusField: String!, $after: String) {{
      {type_query}(login: $owner) {{
        projectV2(number: $number) {{
          items(first: 100, after: $after) {{
            nodes {{
              id
              statusValue: fieldValueByName(name: $statusField) {{
                ... on ProjectV2ItemFieldSingleSelectValue {{
                  name
                }}
              }}
              fieldValueByName(name: $duedate) {{
                ... on ProjectV2ItemFieldDateValue {{
                  date
                }}
              }}
              content {{
                ... on Issue {{
                  id
                  title
                  number
                  url
                  state
                  assignees(first: 10) {{
                    nodes {{
                      email
                      login
                    }}
                  }}
                }}
              }}
            }}
            pageInfo {{
              endCursor
              hasNextPage
            }}
          }}
        }}
      }}
    }}
    """

    variables = {
        "owner": owner,
        "number": int(project_number),
        "duedate": duedate_field_name,
        "statusField": task_status_field_name,
        "after": None
    }

    all_items = []
    has_next_page = True

    while has_next_page:
        try:
            response = requests.post(
                config.api_endpoint,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {config.gh_token}"}
            )
            data = response.json()
        except Exception as e:
            logger.error(f"Errore chiamata ProjectV2: {e}")
            break

        if data.get('errors'):
            logger.error(f"Errore GraphQL Project: {data['errors']}")
            break

        # NAVIGAZIONE SICURA (evita crash se il progetto non esiste)
        res_data = data.get('data', {})
        owner_data = res_data.get(type_query)
        if not owner_data:
            logger.error(f"Impossibile trovare l'owner '{owner}' di tipo '{type_query}'")
            break
            
        project_v2 = owner_data.get('projectV2')
        if not project_v2:
            logger.error(f"Impossibile trovare il Progetto #{project_number} per {owner}")
            break

        items_data = project_v2.get('items', {})
        nodes = items_data.get('nodes', [])
        
        for n in nodes:
            content = n.get('content', {})
            if filters and filters.get('open_only') and content.get('state') != 'OPEN':
                continue
            if filters and filters.get('empty_duedate'):
                if n.get('fieldValueByName'): continue
            
            all_items.append(n)

        page_info = items_data.get('pageInfo', {})
        has_next_page = page_info.get('hasNextPage', False)
        variables['after'] = page_info.get('endCursor')

    return all_items


def add_issue_comment(issueId, comment):
    mutation = """
    mutation AddIssueComment($issueId: ID!, $comment: String!) {
        addComment(input: {subjectId: $issueId, body: $comment}) {
            clientMutationId
        }
    }
    """
    variables = {'issueId': issueId, 'comment': comment}
    response = requests.post(
        config.api_endpoint,
        json={"query": mutation, "variables": variables},
        headers={"Authorization": f"Bearer {config.gh_token}"}
    )
    return response.json().get('data')
