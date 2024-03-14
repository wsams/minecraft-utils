import numpy as np

# Define the vertices of the triangle with coordinates in the format (x, z, y), treating z as vertical
A = np.array([10, 180, -98])
B = np.array([20, 180, -141])
C = np.array([36, 200, -112])

# Function to calculate barycentric coordinates
def barycentric_coordinates(p, a, b, c):
    detT = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
    lambda1 = ((b[2] - c[2]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[2] - c[2])) / detT
    lambda2 = ((c[2] - a[2]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[2] - c[2])) / detT
    lambda3 = 1 - lambda1 - lambda2
    return lambda1, lambda2, lambda3

# Function to check if a point is inside the triangle
def is_inside_triangle(p, a, b, c):
    lambda1, lambda2, lambda3 = barycentric_coordinates(p, a, b, c)
    return 0 <= lambda1 <= 1 and 0 <= lambda2 <= 1 and 0 <= lambda3 <= 1

# Generate points within the bounding box of the triangle and check y (horizontal) dimension range
min_x, max_x = min(A[0], B[0], C[0]), max(A[0], B[0], C[0])
min_y, max_y = min(A[2], B[2], C[2]), max(A[2], B[2], C[2])
# Make sure the minimum z value (vertical) is 180
min_z, max_z = 180, max(A[1], B[1], C[1])

fill_commands = []

for x in range(min_x, max_x + 1):
    for y in range(min_y, max_y + 1):
        for z in range(min_z, max_z + 1):
            p = np.array([x, z, y])  # Correctly using z as the vertical dimension
            if is_inside_triangle(p, A, B, C):
                fill_command = f"fill {x} {z} {y} {x} {z} {y} minecraft:iron_block"
                fill_commands.append(fill_command)

# Print the commands
for command in fill_commands:
    print(command)

