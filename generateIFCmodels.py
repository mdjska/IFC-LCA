from pathlib import Path
import ifcopenshell
import ifcopenshell.api
import pandas as pd
from pprint import pprint
import csv
import json


dir_path = Path(__file__).parent


def load_json_file(file_path):
    with open(file_path, "r") as file:
        return json.load(file)


def import_as_dict(file_path):
    """
    Imports a CSV file and returns the data as a dictionary with the necessary level of nesting.

    Parameters:
    - file_path: The path to the CSV file.
    """
    lca_dict = {}

    with open(file_path, mode="r", encoding="utf-8-sig") as file:
        csv_reader = csv.DictReader(file)
        columns = csv_reader.fieldnames
        set_name_col = columns[0]
        for row in csv_reader:
            if row.get(set_name_col):
                lca_dict[row[set_name_col]] = {
                    k: v for k, v in row.items() if v and k not in [set_name_col]
                }

            # Otherwise, it's a property of the current PropertySet
            else:
                property_details = {
                    k: v for k, v in row.items() if v and k not in [set_name_col]
                }
                if property_details:
                    last_pset_name = list(lca_dict.keys())[-1]
                    if not "Properties" in lca_dict[last_pset_name].keys():
                        lca_dict[last_pset_name]["Properties"] = []
                    lca_dict[last_pset_name]["Properties"].append(property_details)
    return lca_dict


def find_value_by_guid(data, guid, return_key="value"):
    """
    Searches through a nested data structure (dict or list) for a dictionary with a key "guid" that matches the specified guid.
    If a match is found, returns the value associated with the specified return_key in that dictionary. If no match is found, returns None.

    :param data: The nested data structure (dict or list) to search through.
    :param guid: The guid value to search for.
    :param return_key: The key for which to return the value if a match is found. Defaults to "value".
    :return: The value associated with return_key if a match is found; otherwise, None.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "guid" and value == guid:
                return data.get(return_key, None)
            found_value = find_value_by_guid(value, guid, return_key=return_key)
            if found_value is not None:
                return found_value
    elif isinstance(data, list):
        for item in data:
            found_value = find_value_by_guid(item, guid, return_key=return_key)
            if found_value is not None:
                return found_value
    return None


def convert_value_type(data_type, value):
    """
    Dynamically converts a value to the correct Python data type based on the provided IFC data type.

    Parameters:
    - data_type: The IFC data type as a string.
    - value: The value to be converted.

    Returns:
    - The value converted to the corresponding Python data type.
    """
    type_conversion_map = {
        "boolean": lambda x: x.lower() in ["true", "1", "t", "yes"],
        "integer": int,
        "float": float,
        "string": str,
    }

    # IFC data types to Python primitives
    schema = ifcopenshell.ifcopenshell_wrapper.schema_by_name(ifc_model.schema)
    type_decl = schema.declaration_by_name(data_type)
    python_type_name = ifcopenshell.util.attribute.get_primitive_type(type_decl)

    # Retrieve the conversion function from the map using the Python type name
    conversion_func = type_conversion_map.get(
        python_type_name, str
    )  # Default to str conversion
    if value:
        return conversion_func(value)
    else:
        if python_type_name == "boolean":
            return False
        elif python_type_name == "integer":
            return 0
        elif python_type_name == "float":
            return 0.0
        else:
            return "NaN"


def generate_basic_ifc_model(object_class, object_name):
    """
    Generates a basic IFC model with predefined settings and adds an object of a specified class and name to it.
    Creates a project library for non-IfcBuilding objects.

    :param object_class: The class of the object to be added to the IFC model (e.g., "IfcWall", "IfcBeam").
    :param object_name: The name of the object to be added to the IFC model.
    :return: None. The function modifies global variable 'ifc_model' and does not return any value.
    """
    global ifc_model
    ifc_model = ifcopenshell.api.run("project.create_file", version="IFC4x3")
    root_project = ifcopenshell.api.run(
        "root.create_entity",
        ifc_model,
        ifc_class="IfcProject",
        name="CODview2 22057 Demo Library Object",
    )
    if object_class != "IfcBuilding":
        project_library = ifcopenshell.api.run(
            "root.create_entity",
            ifc_model,
            ifc_class="IfcProjectLibrary",
            name="CODview2 22057 Demo Library Object",
        )
        ifcopenshell.api.run(
            "project.assign_declaration",
            ifc_model,
            definition=project_library,
            relating_context=root_project,
        )

    massunit = ifcopenshell.api.run(
        "unit.add_si_unit", ifc_model, unit_type="MASSUNIT", prefix="KILO"
    )
    # adds m, m2 and m3 as length, area and volume units automatically
    ifcopenshell.api.run(
        "unit.assign_unit", ifc_model, length={"is_metric": True, "raw": "METERS"}
    )
    # adds kg as mass unit
    ifcopenshell.api.run("unit.assign_unit", ifc_model, units=[massunit])

    organisation = ifcopenshell.api.run(
        "owner.add_organisation",
        ifc_model,
        identification="https://identifier.buildingsmart.org/uri/LCA",
        name="buildingSMART Sustainability Strategic Group",
    )

    reference_library = ifcopenshell.api.run(
        "library.add_library", ifc_model, name="LCA indicators and modules"
    )
    ifcopenshell.api.run(
        "library.edit_library",
        ifc_model,
        library=reference_library,
        attributes={
            "Version": "3.0",
            "Publisher": organisation,
            "VersionDate": "2023-12-01",
            "Location": "https://identifier.buildingsmart.org/uri/LCA/LCA/3.0",
        },
    )
    global constr_object
    constr_object = ifcopenshell.api.run(
        "root.create_entity", ifc_model, ifc_class=object_class, name=object_name
    )
    if object_class != "IfcBuilding":
        # Mark the building proxy type element as a reusable asset in the project library.
        ifcopenshell.api.run(
            "project.assign_declaration",
            ifc_model,
            definition=constr_object,
            relating_context=project_library,
        )
    return


def add_propertysinglevalue(
    pset, prop_details, unit, raw_value, complex_prop_single=False
):
    """
    Adds an IfcPropertySingleValue to a given property set.

    :param pset: The property set to which the property will be added.
    :param prop_details: Dictionary with details of the property including name and type.
    :param raw_value: The raw value to be converted and added as a value.
    :param complex_prop_list: Boolean flag to indicate whether the property list value is part of a complex property.
    :param unit: Optional unit for the property values.
    """
    try:
        value = convert_value_type(prop_details["DataType"], value=raw_value)
        ifcvalue = ifc_model.create_entity(
            prop_details["DataType"],
            value,
        )
    except ValueError:
        ifcvalue = ifc_model.create_entity(
            "IfcLabel",
            str(raw_value),
        )
    single_prop = ifc_model.createIfcPropertySingleValue(
        Name=prop_details["PropertyName"],
        NominalValue=ifcvalue,
        Unit=unit,
    )
    if not complex_prop_single:
        if pset.HasProperties:
            hasprops_list = list(pset.HasProperties)
            hasprops_list.append(single_prop)
            pset.HasProperties = hasprops_list
        else:
            pset.HasProperties = [single_prop]
    return single_prop


def add_propertylistvalue(
    pset, prop_details, raw_value, unit=None, complex_prop_list=False
):
    """
    Adds an IfcPropertyListValue to a given property set.

    :param pset: The property set to which the property will be added.
    :param prop_details: Dictionary with details of the property including name and type.
    :param raw_value: The raw value to be converted and added as a list value.
    :param complex_prop_list: Boolean flag to indicate whether the property list value is part of a complex property.
    :param unit: Optional unit for the property values.
    """

    # Extract necessary details from prop_details
    prop_name = prop_details["PropertyName"]
    value_type = prop_details["DataType"]

    if raw_value:
        raw_value = raw_value.split(";")
    else:
        raw_value = [None, None]

    # Convert each value in the list to the correct IFC data type
    list_values = [
        ifc_model.create_entity(value_type, convert_value_type(value_type, value))
        for value in raw_value
    ]

    # Create the IfcPropertyListValue with the converted list values
    list_prop = ifc_model.createIfcPropertyListValue(
        Name=prop_name, ListValues=list_values, Unit=unit
    )

    if complex_prop_list:
        return list_prop
    # Return the updated property set with the new property list value
    if pset.HasProperties:
        hasprops_list = list(pset.HasProperties)
        hasprops_list.append(list_prop)
        pset.HasProperties = hasprops_list
    else:
        pset.HasProperties = [list_prop]

    return list_prop


def add_propertyenumeration(penum_name, unit):
    """
    Creates an IFC property enumeration for a specified property enumeration (penum) name and associates it with a unit.

    :param penum_name: The name of the property enumeration (penum) to be used.
    :param unit: The unit to be associated with the enumeration.
    :return: The created IfcPropertyEnumeration entity.
    """
    enumeration_values_list = []
    for enum_details in penums[penum_name]["Properties"]:
        enumeration_values_list.append(
            ifc_model.create_entity(
                enum_details["DataType"],
                convert_value_type(
                    enum_details["DataType"], enum_details["EnumerationValues"]
                ),
            )
        )

    enum = ifc_model.createIfcPropertyEnumeration(
        penum_name, enumeration_values_list, unit
    )
    return enum


def get_data_type_for_enum_value(penum_name, enumeration_value):
    """
    Retrieves the data type associated with a specific enumeration value within a property enumeration (penum).

    :param penum_name: The name of the property enumeration (penum) to search through.
    :param enumeration_value: The enumeration value for which to find the associated data type.
    :return: The data type associated with the enumeration value if found; otherwise, None.
    """
    for prop in penums[penum_name]["Properties"]:
        if prop["EnumerationValues"] == enumeration_value:
            return prop["DataType"]
    return None


def add_propertyenumeratedvalue(
    pset, prop_details, raw_value, unit, complex_prop_enum=False
):
    """
    Adds an IfcPropertyEnumeratedValue to a given property set.

    :param pset: The property set to which the property will be added.
    :param prop_details: Dictionary with details of the property including name and type.
    :param raw_value: The raw value to be converted and added as a value.
    :param complex_prop_list: Boolean flag to indicate whether the property list value is part of a complex property.
    :param unit: Optional unit for the property values.
    """
    penum_name = prop_details["EnumerationReference"]
    if raw_value:
        raw_value = raw_value.split(";")
    else:
        raw_value = [None]

    all_enums = ifc_model.by_type("IfcPropertyEnumeration")
    existing_enum = next((enum for enum in all_enums if enum.Name == penum_name), None)
    enum = existing_enum if existing_enum else add_propertyenumeration(penum_name, unit)

    enumeration_values = []
    for value in raw_value:
        data_type = get_data_type_for_enum_value(penum_name, value)
        if (
            value is None
        ):  # assumes that this is because of 'generate_demo' and takes the first value in the enumeration
            value = penums[penum_name]["Properties"][0]["EnumerationValues"]
            data_type = penums[penum_name]["Properties"][0]["DataType"]
        if data_type:
            converted_value = convert_value_type(data_type, value)
            enumeration_values.append(
                ifc_model.create_entity(data_type, converted_value)
            )
        else:
            print(
                f"Data type for enumeration value '{value}' in '{penum_name}' not found."
            )

    enum_prop = ifc_model.createIfcPropertyEnumeratedValue(
        Name=prop_details["PropertyName"],
        EnumerationValues=enumeration_values,
        EnumerationReference=enum,
    )

    if complex_prop_enum:
        return enum_prop
    if pset.HasProperties:
        hasprops_list = list(pset.HasProperties)
        hasprops_list.append(enum_prop)
        pset.HasProperties = hasprops_list
    else:
        pset.HasProperties = [enum_prop]

    return enum_prop


def add_simpleproperty(pset, prop_details, generate_demo=False, complex_prop=False):
    """
    Adds a simple property to a property set based on provided property details, optionally generating proxy data.

    :param pset: The property set to which the property should be added.
    :param prop_details: A dictionary containing details of the property such as name, type, unit, and GUID.
    :param generate_demo: A boolean flag indicating whether to generate demo data. Defaults to False.
    :param complex_prop: A boolean flag indicating whether the property is should be part of a complex property. Used in delegated functions. Defaults to False.
    :return: The result of the property addition function or None if the IFCType is unsupported.
    """
    raw_value = None
    if not generate_demo and "ISO22057GUID" in prop_details:
        raw_value = find_value_by_guid(product_data, prop_details["ISO22057GUID"])
    if generate_demo or raw_value:
        unit = None
        if "Unit" in prop_details and prop_details["Unit"] != "unitless":
            # example unit: "GIGA PASCAL"
            # gpa = ifc_model.create_entity(
            #     "IfcSIUnit",
            #     Dimensions=None,
            #     UnitType="PRESSUREUNIT",
            #     Prefix="GIGA",
            #     Name="PASCAL",
            # )
            # TODO create or find the right unit
            pass
        if prop_details["IFCType"] == "IfcPropertySingleValue":
            return add_propertysinglevalue(
                pset,
                prop_details,
                raw_value=raw_value,
                unit=unit,
                complex_prop_single=complex_prop,
            )
        elif prop_details["IFCType"] == "IfcPropertyListValue":
            return add_propertylistvalue(
                pset, prop_details, raw_value, unit=unit, complex_prop_list=complex_prop
            )
        elif prop_details["IFCType"] == "IfcPropertyEnumeratedValue":
            return add_propertyenumeratedvalue(
                pset, prop_details, raw_value, unit=unit, complex_prop_enum=complex_prop
            )
        else:
            print(f"Unsupported IFCType: {prop_details['IFCType']}")
            return


def add_complexproperty(pset, prop_details, generate_demo):
    """
    Adds a complex property to a property set (pset) based on provided property details, optionally generating proxy data.

    :param pset: The property set to which the complex property should be added.
    :param prop_details: A dictionary containing the details of the complex property such as its name.
    :param generate_demo: A boolean flag indicating whether to generate demo proxy data.
    :return: None. The function modifies the `pset` object by adding a complex property to it.
    """
    generate_demo_flag = generate_demo
    properties = []
    complex_prop_name = prop_details["PropertyName"]

    all_complex_props = ifc_model.by_type("IfcComplexProperty")
    compelex_prop = next(
        (prop for prop in all_complex_props if prop.Name == complex_prop_name), None
    )

    if not compelex_prop:
        for complex_prop_details in complex_props[complex_prop_name]["Properties"]:
            simple_prop = add_simpleproperty(
                pset,
                complex_prop_details,
                complex_prop=True,
                generate_demo=generate_demo_flag,
            )
            if simple_prop is not None:
                simple_prop.Specification = complex_prop_details["Specification"]
                properties.append(simple_prop)

        if not properties:
            return
        compelex_prop = ifc_model.create_entity(
            "IfcComplexProperty", complex_prop_name, None, complex_prop_name, properties
        )

    if pset.HasProperties:
        hasprops_list = list(pset.HasProperties)
        hasprops_list.append(compelex_prop)
        pset.HasProperties = hasprops_list
    else:
        pset.HasProperties = [compelex_prop]

    return


def add_columns(existing_columns, applicable_columns, existing_references):
    """
    Adds columns to a table, either by reusing existing columns from a provided dictionary or creating new ones.

    :param existing_columns: A dictionary of existing columns, where each key is a column name and each value is the corresponding IfcTableColumn.
    :param applicable_columns: A list of column names that should be added to the table.
    :param existing_references: A dictionary of existing references, where keys are tuples identifying references, and values are the corresponding IfcReference entities.
    :return: A list of IfcTableColumn entities that have been either reused or newly created.
    """
    columns = []
    # Add or reuse "Indicator" column
    if "Indicator" in existing_columns:
        columns.append(existing_columns["Indicator"])
    else:
        columns.append(
            ifc_model.createIfcTableColumn(Identifier="Indicator", Name="Indicator")
        )

    # Add or reuse "Unit" column
    if "Unit" in existing_columns:
        columns.append(existing_columns["Unit"])
    else:
        columns.append(ifc_model.createIfcTableColumn(Identifier="Unit", Name="Unit"))

    for col_name in applicable_columns:
        reference = None
        if "ReferenceTo" in tablecolumns[col_name]:
            ref_key = (
                "IfcBuildingElementProxyType",
                "HasPropertySets",
                tablecolumns[col_name]["ReferenceTo"],
            )
            if ref_key in existing_references:
                reference = existing_references[ref_key]
            else:
                reference = ifc_model.create_entity(
                    "IfcReference",
                    TypeIdentifier="IfcBuildingElementProxyType",
                    AttributeIdentifier="HasPropertySets",
                    InstanceName=tablecolumns[col_name]["ReferenceTo"],
                )
        if col_name in existing_columns:
            column = existing_columns[col_name]  # Reuse existing column
        else:
            column = ifc_model.createIfcTableColumn(
                Identifier=col_name,
                Name=col_name,
                Description=tablecolumns[col_name].get("Description"),
                ReferencePath=reference,
            )
        columns.append(column)
    return columns


def add_rows(prop_details, applicable_columns, generate_demo=False):
    """
    Adds rows to a table based on provided property details, applicable columns, and optionally generating demo proxy values.

    :param prop_details: A dictionary containing details of the rows to be added.
    :param applicable_columns: A list of column names that are applicable to the rows being added.
    :param generate_demo: A boolean flag indicating whether to generate demo data for rows. Defaults to False.
    :return: A list of IfcTableRow entities that have been created for each row.
    """
    rows = []
    for row in prop_details["Properties"]:
        if generate_demo:
            indicator_values = True
        else:
            indicator_values = find_value_by_guid(
                product_data, row["ISO22057GUID"], return_key="values"
            )
        if indicator_values:
            row_cells_entities = [
                ifc_model.create_entity("IfcLabel", row["RowName"]),
                ifc_model.create_entity("IfcLabel", row["Unit"]),
            ]

            for col_name in applicable_columns:
                if generate_demo:
                    raw_value = 0
                else:
                    raw_value = find_value_by_guid(
                        indicator_values, tablecolumns[col_name]["ISO22057GUID"]
                    )
                if raw_value is not None:
                    try:
                        cell_val = ifc_model.create_entity(
                            row["DataType"],
                            convert_value_type(row["DataType"], raw_value),
                        )
                    except ValueError:  # if the value in data is not a number
                        cell_val = ifc_model.create_entity("IfcLabel", str(raw_value))
                else:  # if the value is not found in the data -> rows must have the same number of values as there are columns
                    cell_val = ifc_model.create_entity("IfcLabel", "NaN")
                row_cells_entities.append(cell_val)
            row_entity = ifc_model.create_entity(
                "IfcTableRow", RowCells=row_cells_entities
            )
            rows.append(row_entity)
    return rows


def add_table(prop_details, prop_name, unit=None, generate_demo=False):
    """
    Creates and adds a table to the IFC model based on provided property details, property name, and optional unit.

    :param prop_details: A dictionary containing details of the properties for which the table is being created.
    :param prop_name: The name of the property for which the table is being created.
    :param unit: The unit associated with the properties in the table, if any. Defaults to None.
    :param generate_demo: A boolean flag indicating whether to generate demo proxy data for the table. Defaults to False.
    :return: The created IfcTable entity or None if no rows are added to the table.
    """
    existing_columns = {
        column.Name: column for column in ifc_model.by_type("IfcTableColumn")
    }
    existing_references = {
        (ref.TypeIdentifier, ref.AttributeIdentifier, ref.InstanceName): ref
        for ref in ifc_model.by_type("IfcReference")
    }
    if generate_demo:
        applicable_columns = tablecolumns.keys()

    else:
        EPDMethodologicalSpecification_props = property_sets[
            "LCAPset_EPDMethodologicalSpecification"
        ]["Properties"]
        informationmodule_prop_guid = next(
            (
                item["ISO22057GUID"]
                for item in EPDMethodologicalSpecification_props
                if item["PropertyName"] == "InformationModule"
            ),
            None,
        )
        applicable_columns = find_value_by_guid(
            product_data, informationmodule_prop_guid
        ).split(";")
        applicable_columns = ["D" if x == "D1" else x for x in applicable_columns]

    columns = add_columns(
        existing_columns,
        applicable_columns,
        existing_references,
    )
    rows = add_rows(prop_details, applicable_columns, generate_demo=generate_demo)

    # Check if there are any rows to add
    if not rows:
        print(f"No rows to add for table {prop_name}. Table creation skipped.")
        return None

    table = ifc_model.create_entity(
        "IfcTable", Name=prop_name + "Table", Columns=columns, Rows=rows
    )
    return table


def add_propertyreferencevalue(
    pset, prop_details, prop_name, unit=None, generate_demo=False
):
    """
    Adds an IfcPropertyReferenceValue to a given property set.

    :param pset: The property set to which the property will be added.
    :param prop_details: Dictionary with details of the property including name and type.
    :param prop_name: The name of the property.
    :param unit: Optional unit for the property values. Defaults to None.
    :param complex_prop_list: Boolean flag to indicate whether the property list value is part of a complex property.
    """
    table = add_table(prop_details, prop_name, unit=unit, generate_demo=generate_demo)
    if table is None:
        return None
    ref_prop = ifc_model.createIfcPropertyReferenceValue(
        Name=prop_name, UsageName=prop_name + "Results", PropertyReference=table
    )
    if pset.HasProperties:
        hasprops_list = list(pset.HasProperties)
        hasprops_list.append(ref_prop)
        pset.HasProperties = hasprops_list
    else:
        pset.HasProperties = [ref_prop]
    return ref_prop


def add_environmental_indicators(pset, generate_demo=False):
    """
    Adds environmental indicators as property reference values to a property set (pset).

    :param pset: The property set to which the environmental indicators should be added.
    :param generate_demo: A boolean flag indicating whether to generate demo proxy data for the indicators. Defaults to False.
    :return: None. The function modifies the `pset` object by adding environmental indicators to it.
    """
    for prop_name, prop_details in tablerows.items():
        add_propertyreferencevalue(
            pset,
            prop_details,
            generate_demo=generate_demo,
            prop_name=prop_name,
        )
    return


def main(
    generate_demo,
    ifc_file_name,
    constr_object_class="IfcBuildingElementProxyType",
    object_name="My Demo Object",
):
    """
    Main function to generate a basic IFC model with specified properties and environmental indicators.

    :param generate_demo: A boolean flag indicating whether to generate demo proxy data for the model.
    :param ifc_file_name: The name of the IFC file to be generated.
    :param constr_object_class: The class of the construction object to be added to the model. Defaults to "IfcBuildingElementProxyType".
    :param object_name: The name of the construction object. Defaults to "My Demo Object".
    :return: None. The function writes the generated IFC model to a file.
    """
    # Initialize the basic IFC model and add a construction object to it
    generate_basic_ifc_model(constr_object_class, object_name)
    # Iterate through predefined property sets and add them to the construction object
    for pset_name, pset_details in property_sets.items():
        pset = ifcopenshell.api.run(
            "pset.add_pset", ifc_model, product=constr_object, name=pset_name
        )
        if "Description" in pset_details:
            pset.Description = pset_details["Description"]
        if "Properties" in pset_details:
            for prop_details in pset_details["Properties"]:
                if prop_details["IFCType"] == "IfcComplexProperty":
                    add_complexproperty(pset, prop_details, generate_demo=generate_demo)
                else:
                    prop = add_simpleproperty(
                        pset, prop_details, generate_demo=generate_demo
                    )
                    if prop is not None and "Specification" in prop_details:
                        prop.Specification = prop_details["Specification"]
        if pset_name == "LCAPset_EnvironmentalIndicators":
            add_environmental_indicators(pset, generate_demo=generate_demo)
        if not pset.HasProperties:
            ifcopenshell.api.run(
                "pset.remove_pset", ifc_model, product=constr_object, pset=pset
            )

    dir_path = Path(__file__).parent
    file_path = Path.joinpath(
        dir_path, "GeneratedIFCModels", ifc_file_name
    ).with_suffix(".ifc")
    ifc_model.write(file_path)
    return


file_paths = [
    Path.joinpath(dir_path, "CSV", "FullLCABuildingPsets").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "MVPLCABuildingPsets").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "LCABuildingEnumerations").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "22057IFC_psets").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "22057IFC_enumerations").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "22057IFC_complexprops").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "22057IFC_tablerows").with_suffix(".csv"),
    Path.joinpath(dir_path, "CSV", "22057IFC_tablecolumns").with_suffix(".csv"),
    Path.joinpath(
        dir_path, "Example22057ProductsJSON", "massiv_betonelement_vaeg_iso22057"
    ).with_suffix(".json"),
    Path.joinpath(
        dir_path, "Example22057ProductsJSON", "leca_isoblokk_LSX30_iso22057"
    ).with_suffix(".json"),
]

# property_sets = import_as_dict(file_paths[0])  # Full
# property_sets = import_as_dict(file_paths[1])  # MVP
# penums = import_as_dict(file_paths[2]) # Building
property_sets = import_as_dict(file_paths[3])  # Product
penums = import_as_dict(file_paths[4])  # Product
complex_props = import_as_dict(file_paths[5])
tablerows = import_as_dict(file_paths[6])
tablecolumns = import_as_dict(file_paths[7])
# product_data = load_json_file(file_paths[8]) # massiv_betonelement_vaeg_iso22057
product_data = load_json_file(file_paths[9])  # leca_isoblokk_LSX30_iso22057


# ifc_file_name = "22057IFC_Example_massiv_betonelement"
# ifc_file_name = "22057IFC_Example_leco_isoblokk"
ifc_file_name = "22057IFCDemoObject"
# ifc_file_name = "MVPLCABuildingPsets"
# ifc_file_name = "FullLCABuildingPsets"
generate_demo = True

main(
    generate_demo,
    ifc_file_name,
    constr_object_class="IfcBuilding",
    object_name="My Demo Building",
)
