from queue_manager import QueueManager


def test_queue_file_isolated(tmp_path):
    f_a = tmp_path / "a" / "queue.json"
    f_b = tmp_path / "b" / "queue.json"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    qm_a = QueueManager(queue_file=str(f_a))
    qm_a.ajouter_entreprise("EDF")
    qm_a.sauvegarder()

    qm_b = QueueManager(queue_file=str(f_b))
    qm_b.ajouter_entreprise("Engie")
    qm_b.sauvegarder()

    assert f_a.exists() and f_b.exists()

    reload_a = QueueManager(queue_file=str(f_a))
    reload_a.charger()
    noms = [j.entreprise for j in reload_a.jobs]
    assert noms == ["EDF"]            # n'a PAS chargé la file de b


def test_default_queue_file():
    qm = QueueManager()
    assert qm.queue_file == "config/queue.json"
