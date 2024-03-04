# mkmcfunction.py

## Usage

Create a datapack. In your minecraft world folder create the directory `datapacks/your_data_pack_name/data/io/functions`.

In the directory `your_data_pack_name` create a file `pack.mcmeta` with these contents,

```json
{
  "pack": {
    "pack_format": 3,
    "description": "Custom datapack"
  }
}
```

Now clone this repository and run the `mkmcfunction.py` script on an image file. It can be a `.jpg` or `.png` file, and probably many others. Transparent (alpha channel) pixels will be replaced with `minecraft:air`. After running this script, it will output an `mcfunction` file with the same base name as the image. Copy this `mcfunction` file into your datapaack functions folder.

You will want to open the script and find the `max_dimension` and `offset` variables at the bottom. The `max_dimension` controls the maximum width and height your image will be scaled down to. Either the width or the height will be the `max_dimension`.

The `offset` variable controls where the image will be created. What I do is `/tp 0 ~ 0` and then generate an image. You can fly north or south and generate different images. Once that area is filled I change `offset = 1000` and run `/tp 1000 ~ 1000` and that's where the images will be created. This part is a bit odd so any suggestions are welcome. I want the positioning of these images to be more intuitive and configurable.

```sh
python3 mkmcfunction.py <image.png>
cp image.mcfunction path/to/world/datapacks/your_data_pack_name/data/io/functions/
```

In Minecraft open a terminal and run `reload`. You can also do this from your server command line.

Since we processed `image.png` and created `image.mcfunction` we can run that function in a Minecraft terminal,

```sh
/function io:image
```

Below is a sample screenshot. There's still a lot of work to do.

!screenshots/jug.png!
