{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set base = target.schema if custom_schema_name is none else custom_schema_name | trim -%}
    {%- set namespace = var('build_namespace', '') -%}
    {%- if namespace -%}
        {{ namespace }}_{{ base }}
    {%- else -%}
        {{ base }}
    {%- endif -%}
{%- endmacro %}
