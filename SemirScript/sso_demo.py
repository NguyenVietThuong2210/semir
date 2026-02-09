import os
import secrets
import requests
from flask import Flask, redirect, request, session, jsonify

# ================= CONFIG =================
SSO_SERVER_URI = "https://id.cnv.vn"   # change this
SSO_CLIENT_ID = "4e399845e7944241927e77e837794f1e"
SSO_CLIENT_SECRET = "a4ba379b7037426b9fbb0455725c5979"
SSO_REDIRECT_URI = "http://localhost:5000/callback"

SCOPES = 'read_products,write_products,read_customers,write_customers,read_orders,write_orders'
STATE = 'S5EvfsTTxyvit5vcXqBtx_VYljuwC2aHTRs_vdweZYI'

# Flask setup
app = Flask(__name__)
app.secret_key = os.urandom(32)  # required for session


# ================= STEP 1: GET CODE =================
@app.route("/login")
def login():
    print("🔐 REDIRECTING TO SSO SERVER FOR AUTHORIZATION...")
    params = {
        "client_id": SSO_CLIENT_ID,
        "redirect_uri": SSO_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": STATE,
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    print(query_string)
    result = redirect(f"{SSO_SERVER_URI}/oauth?{query_string}")
    return result


# ================= STEP 2: CALLBACK =================
@app.route("/callback")
def callback():
    print("🔑 RECEIVING AUTHORIZATION CODE...")
    received_state = request.args.get("state")

    # State validation
    if not STATE or STATE != received_state:
        return "Invalid state", 400

    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400

    # Exchange code for token
    token_response = requests.get(
        f"{SSO_SERVER_URI}/oauth/token",
        params={
            "grant_type": "authorization_code",
            "client_id": SSO_CLIENT_ID,
            "client_secret": SSO_CLIENT_SECRET,
            "redirect_uri": SSO_REDIRECT_URI,
            "code": code,
        },
        timeout=10,
    )

    token_response.raise_for_status()
    token = token_response.json()

    print("✅ TOKEN RECEIVED:")
    print(token)
    
    # OUTPUT TOKEN
    return jsonify(token)


@app.route("/verify")
def verify():
    access_token = "694e03907b157b41849ee26e"
    token_type = "TOKEN"

    response = requests.post(
        f"{SSO_SERVER_URI}/auth/verify",
        headers={
            "Accept": "application/json",
            "Authorization": f"{token_type} {access_token}",
        },
    )

    return jsonify(response.json())

# ================= RUN APP =================
if __name__ == "__main__":
    app.run(debug=True)
