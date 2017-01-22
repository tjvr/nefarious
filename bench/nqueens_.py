
# coding: utf-8

# In[26]:

def item(i, l):
    return l[i - 1]


# In[27]:

def drop(n, l):
    return l[n:]


# In[28]:

def concat(l, r):
    return l + r


# In[29]:

def threatens(x, y, a, b):
    return x == a or y == b or abs(x - a) == abs(y - b)


# In[34]:

def check(board, current):
    if len(board) < current:
        return True
    if 8 < item(current, board):
        return False
    if threatens(current, item(current, board), 1, item(1, board)):
        return False
    return check(board, current + 1)


# In[35]:

def valid(board):
    return check(board, 2)


# In[36]:

valid([1, 2, 3, 4, 5, 6, 7, 8])


# In[37]:

valid([4, 2, 7, 3, 6, 8, 5, 1])


# In[39]:

def complete(board):
    if len(board) == 0:
        return complete([1])
    if 8 < item(1, board):
        return complete(concat(
            [1 + item(2, board)],
            drop(2, board)
        ))
    if len(board) == 8 and valid(board):
        return board
    if valid(board):
        return complete(concat([1], board))
    return complete(concat(
            [1 + item(1, board)],
            drop(1, board)
    ))


# In[41]:

import sys


# In[46]:

sys.setrecursionlimit(2000)


# In[48]:

for i in range(200):
    complete([])


# In[49]:

print(complete([]))


# In[ ]:



