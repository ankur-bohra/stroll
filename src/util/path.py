'''
Translates local paths to absolute paths to solve issues regarding where the executable is run from.
'''
import os

# Get the path of this file
root = os.path.dirname(os.path.realpath(__file__)) # This would be src\util

# Get the path of the project root folder
THIS_DIR_DEPTH = 2  # The number of folder levels to go up
while THIS_DIR_DEPTH > 0:
    # Move one level up
    root = os.path.dirname(root)
    THIS_DIR_DEPTH -= 1  # Decrement the depth

def from_root(path):
    '''
    Expands a path relative to the root folder.
    '''
    return os.path.join(root, path)