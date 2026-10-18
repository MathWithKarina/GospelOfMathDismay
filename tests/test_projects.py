from gomd.core.project import Project

def test_project_scene_persistence_and_order(tmp_path):
    root=tmp_path/"lesson"
    project=Project.create(root,"Lesson")
    first=project.scenes[0]; first.text="x=2"; first.normalized_text="икс равен двум"; project.save()
    second=project.add_scene("Second")
    project.move_scene(second.id,-1)
    reopened=Project.open(root)
    assert reopened.scenes[0].id==second.id
    saved_first=next(s for s in reopened.scenes if s.id==first.id)
    assert saved_first.text=="x=2"
    assert saved_first.normalized_text=="икс равен двум"

def test_project_keeps_one_scene_and_delete_is_project_local(tmp_path):
    project=Project.create(tmp_path/"lesson","Lesson")
    external=tmp_path/"keep.wav"; external.write_bytes(b"sample")
    scene=project.scenes[0]; scene.audio_path=str(external); project.save_scene(scene)
    second=project.add_scene("Second")
    project.delete_scene(second.id)
    assert external.exists()
    try: project.delete_scene(scene.id)
    except ValueError: pass
    else: raise AssertionError("should not delete the last remaining scene")

def test_scene_id_path_validation(tmp_path):
    project=Project.create(tmp_path/"lesson","Lesson")
    project.scenes[0].id="../outside"
    try: project.scene_dir(project.scenes[0])
    except ValueError: pass
    else: raise AssertionError("path traversal must be rejected")
