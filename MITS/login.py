"""Streamlit sign-in and account creation page for the sustainability planner."""

import streamlit as st

from auth import authenticate_user, register_user


st.set_page_config(
    page_title="MITS | Sustainability Planner",
    page_icon="🌱",
    layout="centered",
)

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(ellipse at 10% 5%, #e8f4e8 0, transparent 38%),
            #f7f9f6;
    }
    .block-container {
        max-width: 760px;
        padding-top: 3rem;
        padding-bottom: 3rem;
    }
    .intro {
        color: #53645a;
        font-size: 1.05rem;
        margin-top: -0.5rem;
    }
    div.stButton > button[kind="primary"],
    div.stFormSubmitButton > button[kind="primary"] {
        background: #28734e;
        border-color: #28734e;
        border-radius: 0.6rem;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e4ebe4;
        border-radius: 0.8rem;
        padding: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Office Sustainability Action Planner")
st.markdown(
    '<p class="intro">Turn your office audit and sustainability goals into practical, '
    "measurable actions.</p>",
    unsafe_allow_html=True,
)

if "planner_user" not in st.session_state:
    st.session_state.planner_user = None

if st.session_state.planner_user is not None:
    user = st.session_state.planner_user
    _, sign_out_column = st.columns([4, 1])
    with sign_out_column:
        if st.button("Sign out", use_container_width=True):
            st.session_state.planner_user = None
            st.rerun()

    st.success(f"Welcome, {user.full_name}. You are signed in.")
    st.subheader("Your planning workspace")
    st.write(
        "Start with the office audit and existing sustainability goals. "
        "The planner is designed to organize findings into prioritized actions, "
        "owners, resources, and measurable indicators."
    )
    energy, waste, water, paper, transport = st.columns(5)
    for column, label in zip(
        (energy, waste, water, paper, transport),
        ("Energy", "Waste", "Water", "Paper", "Transport"),
    ):
        with column:
            st.metric(label, "Audit area")
else:
    st.divider()
    sign_in_tab, create_account_tab = st.tabs(["Sign in", "Create account"])

    with sign_in_tab:
        st.subheader("Welcome back")
        with st.form("sign_in_form"):
            email = st.text_input("Work email", autocomplete="email")
            password = st.text_input(
                "Password", type="password", autocomplete="current-password"
            )
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True
            )

        if submitted:
            try:
                user = authenticate_user(email, password)
            except ValueError as error:
                st.error(str(error))
            else:
                if user is None:
                    st.error("Email or password is incorrect.")
                else:
                    st.session_state.planner_user = user
                    st.rerun()

    with create_account_tab:
        st.subheader("Create your planner account")
        with st.form("create_account_form"):
            full_name = st.text_input("Full name", autocomplete="name")
            email = st.text_input("Work email", key="register_email", autocomplete="email")
            password = st.text_input(
                "Create password",
                type="password",
                key="register_password",
                autocomplete="new-password",
            )
            confirm_password = st.text_input(
                "Confirm password",
                type="password",
                autocomplete="new-password",
            )
            submitted = st.form_submit_button(
                "Create account", type="primary", use_container_width=True
            )

        if submitted:
            if password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    user = register_user(full_name, email, password)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state.planner_user = user
                    st.rerun()
