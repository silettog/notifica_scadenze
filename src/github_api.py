import requests
import config
from logger import logger

def get_project_issues(owner, owner_type, project_number, duedate_field_name, task_status_field_name, filters=None):
    clean_type = str(owner_type).lower().strip() if owner_type else "organization"
    type_query = "organization" if clean_type == "organization" else "user"

    logger.info(f"Eseguo query GraphQL su {type_query}: {owner}")
    
    query = f"""
    query($owner: String!, $number: Int!, $duedate: String!, $status: String!, $after: String) {{
      {type_query}(login: $owner) {{
        projectV2(number: $number) {{
          items(first: 100, after: $after) {{
            nodes {{
              statusValue: fieldValueByName(name: $status) {{
                ... on ProjectV2ItemFieldSingleSelectValue {{ name }}
              }}
              fieldValueByName(name: $duedate) {{
                ... on ProjectV2ItemFieldDateValue {{ date }}
              }}
              content {{
                __typename
                ... on Issue {{
                  id
                  title
                  number
                  url
                  state
                  assignees(first: 10) {{
                    nodes {{ email login }}
                  }}
                }}
                ... on DraftIssue {{
                  id
                  title
                }}
              }}
            }}
            pageInfo {{ endCursor hasNextPage }}
          }}
        }}
      }}
    }}
    """

    variables = {
        "owner": owner,
        "number": int(project_number),
        "duedate": duedate_field_name,
        "status": task_status_field_name,
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
            
            if "errors" in data:
                logger.error(f"Errore GraphQL: {data['errors']}")
                break

            # Navigazione sicura
            res_data = data.get("data", {}).get(type_query, {}).get("projectV2", {}).get("items", {})
            nodes = res_data.get("nodes", [])
            
            for n in nodes:
                content = n.get("content", {})
                if not content:
                    continue
                
                # Applichiamo il filtro open_only se richiesto
                if filters and filters.get("open_only") and content.get("state") != "OPEN":
                    continue
                    
                all_items.append(n)

            page_info = res_data.get("pageInfo", {})
            has_next_page = page_info.get("hasNextPage", False)
            variables["after"] = page_info.get("endCursor")

        except Exception as e:
            logger.error(f"Errore durante la fetch: {e}")
            break

    return all_items
