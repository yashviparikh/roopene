from streamlit_keycloak import login

def keycloak_login():
    keycloak_user = login(
        server_url="https://<your-keycloak-domain>/auth/",
        realm="your_realm",
        client_id="streamlit-client",
    )
    if keycloak_user:
        return keycloak_user["preferred_username"]
    else:
        return None
