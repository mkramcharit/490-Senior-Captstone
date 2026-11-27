"""A format for canonical category processing used in admin approval and editing."""

# IMPORTS
# re is used to strip prefixes from categories and to split the category into words.
# unicodedata is used to normalize unicode characters prior to formatting.
import re
import unicodedata


# FORMAT CATEGORY NAME
# Normalize to Category:Category_Name. Avoid replicating a prefix.
# The parameter category_name is annotated to be of type str but this does
# not mean it will be checked at runtime.
def format_category_name(category_name: str):
    # TRIM WHITESPACE AND NORMALIZE UNICODE
    # Normalize compatible unicode (e.g. fullwidth characters) to a single form using
    # NFKC.
    # If category_name is None or the empty string use an empty string.
    # Strip whitespace from the beginning and end of the string using strip().
    value = unicodedata.normalize('NFKC', category_name or '').strip()

    # STRIP EXISTING PREFIXES
    # Strip one or more Category: prefixes from the start of the string.
    # Ignore capitalisation of the prefix and allow whitespace before and after the
    # colon and after the colon.
    # This ensures that if a string is in the format Category:Category:historic
    # monuments the output will not contain duplicated prefixes.
    value = re.sub(r'^(?:category\s*:\s*)+', '', value, flags=re.IGNORECASE)

    # SPLIT INTO WORDS
    # Split the string on one or more underscores or whitespace characters.
    # Empty strings resulting from multiple consecutive delimiters are stripped.
    # Other characters are left in the string unchanged.
    words = [word for word in re.split(r'[\s_]+', value) if word]

    # JOIN AND CAPITALIZE WORDS
    # Capitalize each word (first character is uppercase, all other characters are
    # lowercase).
    # Join the words on an underscore and prepend a single Category: prefix.
    # historic monuments will thus become Category:Historic_Monuments.
    # Acronyms are also affected by the capitalize operation. USA will become Usa.
    #
    # EMPTY CATEGORY
    # If a category ends up with no words after stripping prefixes and normalization,
    # None is returned. This means an empty category or a category consisting
    # only of Category: will not result in an incomplete Category: prefix.
    
    return 'Category:' + '_'.join(word.capitalize() for word in words) if words else None
