Data has been pulled from https://huggingface.co/datasets/visheratin/google_landmarks_places 
(for landmark names and locations)
and https://github.com/cvdfoundation/google-landmark (for image urls and unique ids)

Table is organized like so:
    id TEXT
    url TEXT
    landmark_id BIGINT
    category_name TEXT
    name TEXT
    lat DOUBLE PRECISION
    lon DOUBLE PRECISION
    city TEXT
    state TEXT
    country TEXT

where "id" is the unique image id, and "landmark_id" is a non-unique id for each landmark.

"name", "city", "state", and "country" fields may not always be populated. 

Landmark names are separeted into two parts, with "category_name" representing larger 
landmark categories prepended with "Category:" in pascal snake case (ex. Category:Grand_Canyon),
and "name" representing specific landmarks within those larger categories (ex. Bright Angel Suspension Bridge).

"name" field may not be populated if there are no subcategories within "category_name" (ex. )

