import os
import json
from shutil import copyfile

import toml

settings = None
session_data = None


class DataFileInterface:
    def __init__(self):
        self.cache = None
        pass

    def get(self, path, load=False):
        if self.cache is None or load:
            self.load()

        keys = path.split(".")
        cursor = self.cache
        for key in keys:
            if key in cursor:  # Key is valid
                cursor = cursor[key]
            else:
                return None
        return cursor

    def set(self, path, value, dump=False):
        if not self.cache:
            self.load()
        
        keys = path.split(".")
        dict_keys = keys[:len(keys)-1]  # All keys except the last key leads to a dictionary
        cursor = self.cache
        for key in dict_keys:
            cursor = cursor[key]
        last_key = keys[-1]
        cursor[last_key] = value

        if dump:
            self.dump()

    def load(self):
        pass

    def dump(self):
        pass

class DefaultingFile(DataFileInterface):
    def __init__(self, default_file=None):
        super().__init__()
        # default_file is the object with appropriately overloaded load function
        self.default_file = default_file

    def get(self, *args, **kwargs):
        result = super().get(*args, **kwargs)
        # Check the default file for defaults in case of some update
        if result is None and self.default_file:
            # NOTE: It's assumed that None is not acceptable for any value
            alt_result = self.default_file.get(*args, **kwargs)
            if alt_result:
                result = alt_result
        return result

class TomlFile(DefaultingFile):
    def __init__(self, active_file_path, default_file_path=None):
        self.active_path = active_file_path
        self.default_file_path = default_file_path
        default_file = None
        if default_file_path:
            default_file = TomlFile(default_file_path)
        super().__init__(default_file)

    def load(self):
        if os.path.exists(self.active_path):
            self.cache = toml.load(self.active_path)
        else:
            # Copy the default file
            copyfile(self.default_file_path, self.active_path)
            self.load()  # Load in the new file

    def dump(self):
        with open(self.active_path, "w") as file:
            toml.dump(self.cache, file)

class JsonFile(DefaultingFile):
    def __init__(self, active_file_path, default_file_path=None):
        self.active_path = active_file_path
        self.default_file_path = default_file_path
        default_file = None
        if default_file_path:
            default_file = JsonFile(default_file_path)
        super().__init__(default_file)

    def load(self):
        if os.path.exists(self.active_path):
            with open(self.active_path, "r") as file:
                if len(file.read()) > 0:
                    file.seek(0, 0)  # Move the cursor back from the read in the condition
                    self.cache = json.load(file)
                else:
                    self.cache = None
        else:
            # Copy the default file
            copyfile(self.default_file_path, self.active_path)
            self.load()  # Load in the new file

    def dump(self):
        with open(self.active_path, "w") as file:
            json.dump(self.cache, file)
