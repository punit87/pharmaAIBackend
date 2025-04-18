-- Text to SQL original prompt:
-- generate create table scripts for all tables created by the user
CREATE TABLE batch_runs (
    id integer NOT NULL,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp without time zone,
    processed_files integer DEFAULT 0,
    batch_status character varying(20) DEFAULT 'RUNNING'::character varying,
    CONSTRAINT batch_runs_batch_status_check CHECK (((batch_status)::text = ANY ((ARRAY['RUNNING'::character varying, 'SUCCESS'::character varying, 'FAILED'::character varying])::text[])))
);

CREATE TABLE content_blocks (
    id integer NOT NULL,
    batch_run_id integer NOT NULL,
    urs_section_id integer NOT NULL,
    block_number integer NOT NULL,
    content_type character varying(50) NOT NULL,
    content text,
    coord_x1 integer,
    coord_y1 integer,
    coord_x2 integer,
    coord_y2 integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    faiss_index_id integer
);

CREATE TABLE sections (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    section_hash character varying(32) NOT NULL
);

CREATE TABLE skipped_block_items (
    id integer NOT NULL,
    batch_run_id integer NOT NULL,
    parent_block_type character varying(20) NOT NULL,
    skipped_block_type character varying(20) NOT NULL,
    section_name character varying(255),
    parent_block_content character varying(1000),
    skipped_block_content character varying(1000),
    parent_block_coordinates integer[],
    skipped_block_coordinates integer[],
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE urs (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    urs_hash character varying(32) NOT NULL
);

CREATE TABLE urs_section_mapping (
    urs_section_id integer NOT NULL,
    urs_id integer NOT NULL,
    section_id integer NOT NULL
);

CREATE TABLE users (
    id integer NOT NULL,
    name bytea,
    email bytea,
    password character varying(1000),
    activation_link character varying(255),
    activation_token character varying(255),
    active boolean DEFAULT false,
    created_dt timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_dt timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    email_hash text,
    masked_email text
);