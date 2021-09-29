import logging
import os
from typing import Optional

import pystac
from pystac.extensions.eo import EOExtension
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.sar import SarExtension
from pystac.extensions.sat import SatExtension
from stactools.core.io import ReadHrefModifier

from . import Format
from .bands import image_asset_from_href
from .constants import (SENTINEL_CONSTELLATION, SENTINEL_LICENSE,
                        SENTINEL_PROVIDER)
from .metadata_links import MetadataLinks
from .product_metadata import ProductMetadata
from .properties import (fill_proj_properties, fill_sar_properties,
                         fill_sat_properties)

logger = logging.getLogger(__name__)


def create_item(
    granule_href: str,
    read_href_modifier: Optional[ReadHrefModifier] = None,
    archive_format: Format = Format.SAFE,
) -> pystac.Item:
    """Create a STC Item from a Sentinel-1 GRD scene.

    Args:
        granule_href (str): The HREF to the granule.
            This is expected to be a path to a SAFE archive (see format for other options).
        read_href_modifier: A function that takes an HREF and returns a modified HREF.
            This can be used to modify a HREF to make it readable, e.g. appending
            an Azure SAS token or creating a signed URL.
        archive_format: An enum specifying the format of the granule. Currently supported formats
            are SAFE (default) and COG.


    Returns:
        pystac.Item: An item representing the Sentinel-1 GRD scene.
    """

    metalinks = MetadataLinks(granule_href, read_href_modifier, archive_format)

    product_metadata = ProductMetadata(
        metalinks.product_metadata_href,
        metalinks.grouped_hrefs,
        metalinks.map_filename,
        read_href_modifier,
    )

    item = pystac.Item(
        id=product_metadata.scene_id,
        geometry=product_metadata.geometry,
        bbox=product_metadata.bbox,
        datetime=product_metadata.get_datetime,
        properties={},
        stac_extensions=[],
    )

    # ---- Add Extensions ----
    # sar
    sar = SarExtension.ext(item, add_if_missing=True)
    fill_sar_properties(sar, metalinks.product_metadata_href,
                        product_metadata.resolution, read_href_modifier)

    # sat
    sat = SatExtension.ext(item, add_if_missing=True)
    fill_sat_properties(sat, metalinks.product_metadata_href,
                        read_href_modifier)

    # eo
    EOExtension.ext(item, add_if_missing=True)

    # proj
    proj = ProjectionExtension.ext(item, add_if_missing=True)
    fill_proj_properties(proj, metalinks, product_metadata, read_href_modifier)
    proj.geometry = None  # Remove "proj:geometry", it's identical to "geometry"

    # --Common metadata--
    item.common_metadata.providers = [SENTINEL_PROVIDER]
    item.common_metadata.platform = product_metadata.platform
    item.common_metadata.constellation = SENTINEL_CONSTELLATION

    # s1 properties
    item.properties.update({**product_metadata.metadata_dict})

    # Add assets to item
    item.add_asset(*metalinks.create_manifest_asset())

    # Annotations for bands
    for asset_obj in metalinks.create_product_asset():
        item.add_asset(asset_obj[0], asset_obj[1])

    # Calibrations for bands
    for asset_obj in metalinks.create_calibration_asset():
        item.add_asset(asset_obj[0], asset_obj[1])

    # Noise for bands
    for asset_obj in metalinks.create_noise_asset():
        item.add_asset(asset_obj[0], asset_obj[1])

    # Thumbnail
    if metalinks.thumbnail_href is not None:
        item.add_asset(
            "thumbnail",
            pystac.Asset(
                href=metalinks.thumbnail_href,
                media_type=pystac.MediaType.PNG,
                roles=["thumbnail"],
            ),
        )

    image_assets = dict([
        image_asset_from_href(
            os.path.join(granule_href, image_path),
            item,
        ) for image_path in product_metadata.image_paths
    ])

    for key, asset in image_assets.items():
        assert key not in item.assets
        item.add_asset(key, asset)

    # --Links--
    item.links.append(SENTINEL_LICENSE)

    return item
