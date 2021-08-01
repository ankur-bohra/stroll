'''
Translates local paths to absolute paths to solve issues regarding where the executable is run from.
'''
import os

# The compiled version has a different extension, easy!
is_built = __file__.endswith(".pyc")

# Get the path of this file
# This would be root\src\util for source and root\util for built
root = os.path.dirname(__file__)
# Get the path of the project root folder
# In the built version, program is compiled to a location like this: \\dist\\stroll\\util\\path.pyc => DEPTH = 1
# In the source version, the file is inside util inside of src => DEPTH=2
depth_from_root = 1 if is_built else 2
while depth_from_root > 0:
    # Move one level up
    root = os.path.dirname(root)
    depth_from_root -= 1  # Decrement the depth


def from_root(path):
    '''
    Expands a path relative to the root folder.
    '''
    return os.path.join(root, path)
