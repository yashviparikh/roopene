import streamlit_authenticator as stauth

hashed = stauth.Hasher(['Admin@123']).generate()
print(hashed)
