import struct


def read_stl_raw_vertices(filename):
    with open(filename, "rb") as f:
        header = f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]
        print(f"Number of triangles: {num_triangles}")

        for _ in range(num_triangles):
            f.read(12)
            for _ in range(3):
                vertex = struct.unpack("<fff", f.read(12))
                print(f"Vertex: {vertex}")
            f.read(2)


def read_stl_shifted_vertices(filename):
    vertices = []

    with open(filename, "rb") as f:
        header = f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]

        for _ in range(num_triangles):
            f.read(12)
            for _ in range(3):
                vertex = struct.unpack("<fff", f.read(12))
                vertices.append(vertex)
            f.read(2)

    min_z = min(vertices, key=lambda x: x[2])[2]
    z_shift = 65 - min_z

    shifted_vertices = [(x + z_shift, z + z_shift, y + z_shift) for x, y, z in vertices]

    return shifted_vertices


def read_stl_shifted_triangles(filename):
    triangles = []  # Store triangles as lists of vertices

    with open(filename, "rb") as f:
        header = f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]

        for _ in range(num_triangles):
            f.read(12)  # Ignore the normal vector
            triangle = [
                struct.unpack("<fff", f.read(12)) for _ in range(3)
            ]  # Read vertices of a triangle
            triangles.append(triangle)
            f.read(2)  # Skip the attribute byte count

    # Find the minimum z value across all vertices
    all_vertices = [vertex for triangle in triangles for vertex in triangle]
    min_z = min(all_vertices, key=lambda x: x[2])[2]
    z_shift = 65 - min_z

    # Apply the z-shift to all vertices
    shifted_triangles = []
    for triangle in triangles:
        shifted_triangle = [
            (x, y, z + z_shift) for x, y, z in triangle
        ]  # Shift z, keep x and y as is
        shifted_triangles.append(shifted_triangle)

    return shifted_triangles


def read_and_scale_binary_stl(input_filename, output_filename, scale_factor):
    with open(input_filename, "rb") as stl_file:
        header = stl_file.read(80)
        num_triangles = struct.unpack("<I", stl_file.read(4))[0]
        new_triangles = []

        for _ in range(num_triangles):
            data = stl_file.read(50)
            normal = struct.unpack("<fff", data[:12])
            vertices = [
                struct.unpack("<fff", data[12 + 12 * i : 24 + 12 * i]) for i in range(3)
            ]

            scaled_vertices = [
                (v[0] * scale_factor, v[1] * scale_factor, v[2] * scale_factor)
                for v in vertices
            ]

            new_triangle = struct.pack("<fff", *normal) + b"".join(
                struct.pack("<fff", *v) for v in scaled_vertices
            )
            new_triangle += data[48:]
            new_triangles.append(new_triangle)

    with open(output_filename, "wb") as new_stl_file:
        new_stl_file.write(header)
        new_stl_file.write(struct.pack("<I", num_triangles))
        for triangle in new_triangles:
            new_stl_file.write(triangle)


def sign(p1, p2, p3):
    return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])


def point_in_triangle(pt, v1, v2, v3):
    b1 = sign(pt, v1, v2) < 0.0
    b2 = sign(pt, v2, v3) < 0.0
    b3 = sign(pt, v3, v1) < 0.0
    return (b1 == b2) and (b2 == b3)


def fill_triangle(v1, v2, v3):
    points = []
    # Convert to (x, y) for simplicity, assume z is vertical
    vertices = [(v1[0], v1[1]), (v2[0], v2[1]), (v3[0], v3[1])]
    # Calculate bounding box
    x_min = min(vertices, key=lambda x: x[0])[0]
    x_max = max(vertices, key=lambda x: x[0])[0]
    y_min = min(vertices, key=lambda x: x[1])[1]
    y_max = max(vertices, key=lambda x: x[1])[1]

    # Iterate over each point in the bounding box
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            if point_in_triangle((x, y), *vertices):
                # For each point inside the triangle, add the corresponding Minecraft coordinates
                points.append(
                    (x, y, max(v1[2], v2[2], v3[2]))
                )  # Assuming Z is vertical and taking the max as an example

    return points


input_stl = "foot.stl"
output_stl = "foot-x50.stl"
scale_factor = 20.0
read_and_scale_binary_stl(input_stl, output_stl, scale_factor)

# filename = "foot-x50.stl"
# shifted_vertices = read_stl_shifted_vertices(filename)
# for vertex in shifted_vertices:
#     x, y, z = vertex
#     x = round(x)
#     y = round(y)
#     z = round(z)
#     print(f"fill {x} {y} {z} {x} {y} {z} minecraft:yellow_wool")

# max commands 65536 - TODO: need to split up the file in chunks - multiple mcfunctions (are there ways to run even more?)
filename = "foot-x50.stl"
shifted_triangles = read_stl_shifted_triangles(filename)
for triangle in shifted_triangles:
    x, y, z = triangle
    x1, y1, z1 = x
    x1 = round(x1)
    y1 = round(y1)
    z1 = round(z1)
    x2, y2, z2 = y
    x2 = round(x2)
    y2 = round(y2)
    z2 = round(z2)
    x3, y3, z3 = z
    x3 = round(x3)
    y3 = round(y3)
    z3 = round(z3)
    print(f"fill {x1} {y1} {z1} {x1} {y1} {z1} minecraft:purple_wool")
    print(f"fill {x2} {y2} {z2} {x2} {y2} {z2} minecraft:purple_wool")
    print(f"fill {x3} {y3} {z3} {x3} {y3} {z3} minecraft:purple_wool")
    fills = fill_triangle((x1, y1, z1), (x2, y2, z2), (x3, y3, z3))
    for fill in fills:
        x, y, z = fill
        print(f"fill {x} {y} {z} {x} {y} {z} minecraft:yellow_wool")
