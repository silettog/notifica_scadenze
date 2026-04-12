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

    response = requests.post(
        config.api_endpoint,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {config.gh_token}"}
    )
    
    data = response.json()
    if data.get('errors'):
        logger.error(f"Errore GraphQL: {data['errors']}")
        return issues or []

    res_data = data.get('data').get('repository').get('issues')
    pageinfo = res_data.get('pageInfo')
    
    if issues is None:
        issues = []
    
    issues.extend(res_data.get('nodes'))

    if pageinfo.get('hasNextPage'):
        # CORREZIONE: Aggiunto duedate_field_name nella ricorsione
        return get_repo_issues(owner, repository, duedate_field_name, pageinfo.get('endCursor'), issues)

    return issues


def get_project_issues(owner, owner_type, project_number, duedate_field_name, task_status_field_name, filters=None):
    """
    Recupera le issue direttamente da un Project (V2), usato solitamente in ambiente Enterprise.
    """
    # Determiniamo se il proprietario è un'organizzazione o un utente
    is_org = str(owner_type).strip().lower() == "organization"
    type_query = "organization" if is_org else "user"
    
    query = f"""
    query($owner: String!, $number: Int!, $duedate: String!, $after: String) {{
      {type_query}(login: $owner) {{
        projectV2(number: $number) {{
          items(first: 100, after: $after) {{
            nodes {{
              id
              statusValue: fieldValueByName(name: "{task_status_field_name}") {{
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
        "after": None
    }

    all_items = []
    has_next_page = True

    while has_next_page:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"}
        )
        
        data = response.json()
        if data.get('errors'):
            logger.error(f"Errore ProjectV2: {data['errors']}")
            break

        project_data = data.get('data').get(type_query).get('projectV2').get('items')
        nodes = project_data.get('nodes')
        
        # Filtraggio base (Open issues only se richiesto)
        for n in nodes:
            content = n.get('content', {})
            # Se filters['open_only'] è True, saltiamo le issue chiuse
            if filters and filters.get('open_only') and content.get('state') != 'OPEN':
                continue
            # Se filters['empty_duedate'] è True, prendiamo solo quelle senza data
            if filters and filters.get('empty_duedate'):
                if n.get('fieldValueByName'): continue
            
            all_items.append(n)

        page_info = project_data.get('pageInfo')
        has_next_page = page_info.get('hasNextPage')
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
