from utils.user_context import resolve_user_email, user_paths_for


def test_wiring_uses_resolved_email(tmp_path):
    # Simule l'en-tête Cloudflare → chemins isolés
    email = resolve_user_email(
        {"Cf-Access-Authenticated-User-Email": "carol@corp.com"}, None
    )
    paths = user_paths_for(email, root=str(tmp_path))
    assert "carol" not in str(paths.base)      # dossier = hash, pas l'email
    assert paths.cookie_file.parent.is_dir()
