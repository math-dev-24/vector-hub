-- Nettoie uniquement la copie corrigée. La source original_text reste immuable.
UPDATE pages
SET corrected_text = replace(
    replace(
        replace(
            replace(corrected_text, char(61482), '•'),
            char(61623), '•'
        ),
        char(61607), '▪'
    ),
    char(61656), '➢'
)
WHERE corrected_text LIKE '%' || char(61482) || '%'
   OR corrected_text LIKE '%' || char(61623) || '%'
   OR corrected_text LIKE '%' || char(61607) || '%'
   OR corrected_text LIKE '%' || char(61656) || '%';
