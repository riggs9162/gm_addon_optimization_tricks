import os
from srctools.mdl import Model
from srctools.vmt import Material
from srctools.filesys import RawFileSystem

model_formats = [
    ".mdl",
    ".vvd",
    ".phy",
    ".vtx",
    ".ani",
    ".sw.vtx",
    ".dx80.vtx",
    ".dx90.vtx",
    ".xbox.vtx",
]

def unused_content(path, remove=False, searchLuaModels=True):
    unused_sizes = 0
    unused_count = 0
    fs = RawFileSystem(path)

    # Find all the models in the filesystem
    all_models = []
    all_model_vmts = {}
    vmt_used_count = {}
    vmf_used_count = {}
    for file in fs.walk_folder(''):
        if file.path.endswith('.mdl'):
            all_models.append(file.path)

            all_model_vmts[file.path] = all_model_vmts.get(file.path, [])
            model = Model(fs, fs[file.path])
            for tex in model.iter_textures():
                # append path relative to the input path
                all_model_vmts[file.path].append(tex)
                vmt_used_count[tex] = vmt_used_count.get(tex, 0) + 1

    # Find all the vtfs of the all_model_vmts vmts
    all_model_vtfs = {}
    all_vtfs = []
    for model, vmts in all_model_vmts.items():
        for vmt_path in vmts:
            vmt_full_path = os.path.join(path, vmt_path)
            if os.path.exists(vmt_full_path):
                with open(vmt_full_path, "r", encoding="utf-8") as f:
                    vmt = Material.parse(f, filename=vmt_path)
                for vmtfield in vmt.items():
                    if vmtfield[0].startswith("$basetexture"):
                        vtf = os.path.normpath(vmtfield[1])
                        all_model_vtfs[model] = all_model_vtfs.get(model, [])
                        all_model_vtfs[model].append(vtf)
                        all_vtfs.append(vtf)
                        vmf_used_count[vtf] = vmf_used_count.get(vtf, 0) + 1

    # Find all the models used in lua files
    if searchLuaModels:
        all_lua_used_models = []
        for file in fs.walk_folder('lua'):
            if file.path.endswith('.lua'):
                lua_file_path = os.path.join(path, file.path)
                if os.path.exists(lua_file_path):
                    with open(lua_file_path, "r", encoding="utf-8") as f:
                        lua_contents = f.read()
                        lua_contents = lua_contents.lower()
                        for model in all_models:
                            if model in lua_contents:
                                all_lua_used_models.append(model)

        # print not used models
        print("Unused models:")
        unused_models = []
        for model in all_models:
            if model not in all_lua_used_models:
                no_ext_model = os.path.splitext(model)[0]
                for ext in model_formats:
                    format_path = os.path.join(path, no_ext_model + ext)
                    if os.path.exists(format_path):
                        if ext == ".mdl":
                            unused_models.append(model)

                            for vmt in all_model_vmts[model]:
                                vmt_used_count[vmt] -= 1

                            for vtf in all_model_vtfs.get(model, []):
                                vmf_used_count[vtf] -= 1

                        print("Found unused file:", format_path)
                        unused_sizes += os.path.getsize(format_path)
                        unused_count += 1
                        if remove:
                            os.remove(format_path)
                            print("Removed", format_path)

    # Find all the vmts that no longer get used.
    # Rather than only iterating vmts known from models (vmt_used_count keys),
    # scan the 'materials' folder for all .vmt files and treat any whose
    # used count is 0 (or missing) as unused. This catches .vmt files that
    # exist on disk but are never referenced by any model.
    unused_vmts = []
    all_vmts_in_fs = []
    for file in fs.walk_folder('materials'):
        if file.path.endswith('.vmt'):
            # file.path is relative to the addon root, e.g. 'materials/foo/bar.vmt'
            all_vmts_in_fs.append(file.path)

    # Determine which VMTS are unused (exist on disk and have no model refs).
    unused_vmts = []
    for vmt in all_vmts_in_fs:
        if vmt_used_count.get(vmt, 0) == 0:
            vmt_file_path = os.path.join(path, vmt)
            if os.path.exists(vmt_file_path):
                unused_vmts.append(vmt)

    # Collect directories that contain vmt files
    unused_dirs = []
    vmt_dirs = {}
    for vmt in all_vmts_in_fs:
        d = os.path.dirname(vmt)
        vmt_dirs.setdefault(d, []).append(vmt)

    # Determine directories where all .vmt files are unused. We'll print the
    # directory only in that case, and avoid printing the individual files to
    # reduce noise. For counting/sizing, we'll still include the files so the
    # totals remain accurate.
    unused_dir_set = set()
    for d, vmts in vmt_dirs.items():
        if all(v in unused_vmts for v in vmts):
            dir_full = os.path.join(path, d)
            if os.path.exists(dir_full):
                unused_dirs.append(d)
                unused_dir_set.add(d)

    # Report unused files that are NOT part of an entirely-unused directory.
    # For files inside entirely-unused directories, we'll report the directory
    # only below.
    for vmt in all_vmts_in_fs:
        parent = os.path.dirname(vmt)
        if vmt in unused_vmts and parent not in unused_dir_set:
            vmt_file_path = os.path.join(path, vmt)
            unused_sizes += os.path.getsize(vmt_file_path)
            unused_count += 1
            print("Found unused file:", vmt_file_path)
            if remove:
                try:
                    os.remove(vmt_file_path)
                    print("Removed", vmt)
                except OSError:
                    pass

    # Now report and optionally remove entire unused directories.
    for d in unused_dirs:
        dir_full = os.path.join(path, d)
        # Add sizes/counts for all vmt files in this directory
        for vmt in vmt_dirs.get(d, []):
            vmt_file_path = os.path.join(path, vmt)
            if os.path.exists(vmt_file_path):
                unused_sizes += os.path.getsize(vmt_file_path)
                unused_count += 1
        print("Found unused material directory:", dir_full)
        if remove:
            # Remove files first, then attempt to remove directories.
            for vmt in vmt_dirs.get(d, []):
                vmt_file_path = os.path.join(path, vmt)
                try:
                    if os.path.exists(vmt_file_path):
                        os.remove(vmt_file_path)
                except OSError:
                    pass
            try:
                os.removedirs(dir_full)
                print("Removed directory:", dir_full)
            except OSError:
                # Could not remove (not empty or permission issues) -- skip
                pass

    unused_vtfs = []
    for vtf_used in vmf_used_count:
        if vmf_used_count[vtf_used] == 0:
            vtf_used = "materials/" + vtf_used + ".vtf"
            if os.path.exists(os.path.join(path, vtf_used)):
                unused_vtfs.append(vtf_used)
                unused_sizes += os.path.getsize(os.path.join(path, vtf_used))
                unused_count += 1
                print("Found unused file:", os.path.join(path, vtf_used))
                if remove:
                    os.remove(os.path.join(path, vtf_used))
                    print("Removed", vtf_used)
            
    return unused_sizes, unused_count
