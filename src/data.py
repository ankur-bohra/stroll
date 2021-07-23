import pickle
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

class Settings(DataFileInterface):
    def load(self):
        self.cache = toml.load("settings.toml")

    def dump(self):
        with open("settings.toml", "w") as file:
            toml.dump(self.cache, file)

class SessionData(DataFileInterface):
    def load(self):
        with open("data\\session.dat", "rb") as file:
            if len(file.read()) > 0:
                file.seek(0, 0)  # The read above shifted the cursor
                self.cache = pickle.load(file)
            else:
                self.cache = None
    
    def dump(self):
        with open("data\\session.dat", "wb") as file:
            pickle.dump(self.cache, file)