--
-- PostgreSQL database dump
--

\restrict H7LcAr3giEU4f23SDDhEgtjlFexXHZoEmhCQtItj8QItb7uBcfPjTCyMFuatVxf

-- Dumped from database version 14.19
-- Dumped by pg_dump version 16.10 (Ubuntu 16.10-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: wms
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO wms;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: wms
--

COMMENT ON SCHEMA public IS '';


--
-- Name: movementtype; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.movementtype AS ENUM (
    'RECEIPT',
    'SHIPMENT',
    'TRANSFER',
    'ADJUSTMENT'
);


ALTER TYPE public.movementtype OWNER TO wms;

--
-- Name: batches_fill_expire_at(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.batches_fill_expire_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF TG_OP IN ('INSERT','UPDATE') THEN
    IF NEW.expire_at IS NULL
       AND NEW.production_date IS NOT NULL
       AND NEW.shelf_life_days IS NOT NULL
    THEN
      IF NEW.shelf_life_days < 0 THEN
        RAISE EXCEPTION 'shelf_life_days must be >= 0';
      END IF;
      NEW.expire_at := NEW.production_date + (NEW.shelf_life_days || ' days')::interval;
      NEW.expire_at := date_trunc('day', NEW.expire_at)::date; -- 去时间分量
    END IF;
  END IF;
  RETURN NEW;
END
$$;


ALTER FUNCTION public.batches_fill_expire_at() OWNER TO wms;

--
-- Name: left(jsonb, integer); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public."left"(jsonb, integer) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$ SELECT left(($1)::text, $2) $_$;


ALTER FUNCTION public."left"(jsonb, integer) OWNER TO wms;

--
-- Name: locations_fill_code(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.locations_fill_code() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF NEW.code IS NULL OR NEW.code = '' THEN
            NEW.code := NEW.name;
          END IF;
          RETURN NEW;
        END;
        $$;


ALTER FUNCTION public.locations_fill_code() OWNER TO wms;

--
-- Name: pick_task_lines_auto_status(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.pick_task_lines_auto_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF NEW.picked_qty <= 0 THEN
        NEW.status := 'OPEN';
      ELSIF NEW.picked_qty < NEW.req_qty THEN
        NEW.status := 'PARTIAL';
      ELSE
        NEW.status := 'DONE';
      END IF;
      NEW.updated_at := now();
      RETURN NEW;
    END$$;


ALTER FUNCTION public.pick_task_lines_auto_status() OWNER TO wms;

--
-- Name: pick_tasks_aggregate_status(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.pick_tasks_aggregate_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      remain INT;
    BEGIN
      SELECT COUNT(*) INTO remain
      FROM pick_task_lines
      WHERE task_id = NEW.task_id
        AND status NOT IN ('DONE','CANCELLED');
      IF remain = 0 THEN
        UPDATE pick_tasks SET status='DONE', updated_at=now()
        WHERE id = NEW.task_id AND status <> 'DONE';
      ELSE
        UPDATE pick_tasks SET updated_at=now()
        WHERE id = NEW.task_id;
      END IF;
      RETURN NULL;
    END$$;


ALTER FUNCTION public.pick_tasks_aggregate_status() OWNER TO wms;

--
-- Name: snapshot_today(); Type: PROCEDURE; Schema: public; Owner: wms
--

CREATE PROCEDURE public.snapshot_today()
    LANGUAGE plpgsql
    AS $$
BEGIN
  WITH r AS (
    SELECT item_id, location_id, COALESCE(SUM(qty),0)::int AS reserved
    FROM reservations
    WHERE status='ACTIVE'
    GROUP BY item_id, location_id
  ),
  s AS (
    SELECT item_id, location_id, warehouse_id, COALESCE(SUM(qty),0)::int AS on_hand
    FROM stocks
    GROUP BY item_id, location_id, warehouse_id
  ),
  sv AS (
    SELECT
      now()                             AS as_of_ts,
      s.item_id,
      s.location_id,
      (s.on_hand)::numeric              AS qty,
      now()                             AS created_at,
      CURRENT_DATE                      AS snapshot_date,
      s.on_hand                         AS qty_on_hand,
      GREATEST(s.on_hand - COALESCE(r.reserved,0), 0) AS qty_available,
      s.warehouse_id                    AS warehouse_id,
      now()                             AS updated_at,
      NULL::int                         AS batch_id,
      0                                 AS qty_allocated,
      NULL::date                        AS expiry_date,
      NULL::int                         AS age_days
    FROM s
    LEFT JOIN r USING (item_id, location_id)
  )
  INSERT INTO stock_snapshots (
    as_of_ts, item_id, location_id, qty, created_at, snapshot_date,
    qty_on_hand, qty_available, warehouse_id, updated_at,
    batch_id, qty_allocated, expiry_date, age_days
  )
  SELECT * FROM sv
  ON CONFLICT ON CONSTRAINT uq_stock_snapshots_cut_item_loc
  DO UPDATE SET
    qty            = EXCLUDED.qty,
    qty_on_hand    = EXCLUDED.qty_on_hand,
    qty_available  = EXCLUDED.qty_available,
    warehouse_id   = EXCLUDED.warehouse_id,
    updated_at     = now();
END;
$$;


ALTER PROCEDURE public.snapshot_today() OWNER TO wms;

--
-- Name: stocks_qty_sync(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.stocks_qty_sync() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          -- 互补：谁为 NULL 就用另一列补上
          IF NEW.qty IS NULL AND NEW.qty_on_hand IS NOT NULL THEN
            NEW.qty := NEW.qty_on_hand;
          ELSIF NEW.qty_on_hand IS NULL AND NEW.qty IS NOT NULL THEN
            NEW.qty_on_hand := NEW.qty;
          END IF;

          -- 保证一致：若两者都不为空但不同，以 NEW.qty 为准镜像到 qty_on_hand
          -- （也可反过来，以业务决定；我们统一以 qty 为唯一事实源）
          IF NEW.qty IS NOT NULL THEN
            NEW.qty_on_hand := NEW.qty;
          END IF;

          RETURN NEW;
        END
        $$;


ALTER FUNCTION public.stocks_qty_sync() OWNER TO wms;

--
-- Name: tg_stock_ledger_fill_item_id(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.tg_stock_ledger_fill_item_id() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF NEW.item_id IS NULL THEN
            SELECT s.item_id INTO NEW.item_id
            FROM public.stocks s
            WHERE s.id = NEW.stock_id;
          END IF;
          RETURN NEW;
        END;
        $$;


ALTER FUNCTION public.tg_stock_ledger_fill_item_id() OWNER TO wms;

--
-- Name: touch_updated_at(); Type: FUNCTION; Schema: public; Owner: wms
--

CREATE FUNCTION public.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              NEW.updated_at = NOW();
              RETURN NEW;
            END
            $$;


ALTER FUNCTION public.touch_updated_at() OWNER TO wms;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.alembic_version (
    version_num character varying(255) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO wms;

--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.audit_events (
    id bigint NOT NULL,
    category character varying(64) NOT NULL,
    ref character varying(128) NOT NULL,
    meta jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.audit_events OWNER TO wms;

--
-- Name: audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.audit_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.audit_events_id_seq OWNER TO wms;

--
-- Name: audit_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.audit_events_id_seq OWNED BY public.audit_events.id;


--
-- Name: batches; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.batches (
    id integer NOT NULL,
    item_id integer NOT NULL,
    batch_code character varying(64) NOT NULL,
    qty integer DEFAULT 0 NOT NULL,
    expire_at date,
    mfg_date date,
    supplier_lot text,
    expiry_date date,
    production_date date,
    shelf_life_days integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.batches OWNER TO wms;

--
-- Name: COLUMN batches.expire_at; Type: COMMENT; Schema: public; Owner: wms
--

COMMENT ON COLUMN public.batches.expire_at IS '到期日（FEFO）';


--
-- Name: batches_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.batches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.batches_id_seq OWNER TO wms;

--
-- Name: batches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.batches_id_seq OWNED BY public.batches.id;


--
-- Name: channel_inventory; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.channel_inventory (
    id integer NOT NULL,
    store_id integer NOT NULL,
    item_id integer NOT NULL,
    cap_qty integer,
    reserved_qty integer DEFAULT 0 NOT NULL,
    visible_qty integer DEFAULT 0 NOT NULL,
    visible integer,
    CONSTRAINT ck_channel_inventory_reserved_nonneg CHECK ((reserved_qty >= 0)),
    CONSTRAINT ck_channel_inventory_visible_nonneg CHECK ((visible_qty >= 0))
);


ALTER TABLE public.channel_inventory OWNER TO wms;

--
-- Name: channel_inventory_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.channel_inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.channel_inventory_id_seq OWNER TO wms;

--
-- Name: channel_inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.channel_inventory_id_seq OWNED BY public.channel_inventory.id;


--
-- Name: channel_reserve_ops_backup_20251109; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.channel_reserve_ops_backup_20251109 (
    id integer NOT NULL,
    store_id integer NOT NULL,
    ext_order_id character varying(64) NOT NULL,
    ext_sku_id character varying(64) NOT NULL,
    op character varying(16) DEFAULT 'RESERVE'::character varying NOT NULL,
    qty integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.channel_reserve_ops_backup_20251109 OWNER TO wms;

--
-- Name: channel_reserve_ops_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.channel_reserve_ops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.channel_reserve_ops_id_seq OWNER TO wms;

--
-- Name: channel_reserve_ops_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.channel_reserve_ops_id_seq OWNED BY public.channel_reserve_ops_backup_20251109.id;


--
-- Name: channel_reserved_idem_backup_20251109; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.channel_reserved_idem_backup_20251109 (
    ref text NOT NULL,
    store_id bigint,
    item_id bigint,
    delta integer,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.channel_reserved_idem_backup_20251109 OWNER TO wms;

--
-- Name: event_error_log; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.event_error_log (
    id integer NOT NULL,
    dedup_key text NOT NULL,
    stage text NOT NULL,
    error text NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    meta jsonb NOT NULL,
    platform character varying(32) NOT NULL,
    shop_id character varying(64) NOT NULL,
    order_no character varying(128) NOT NULL,
    idempotency_key character varying(256) NOT NULL,
    from_state character varying(32),
    to_state character varying(32) NOT NULL,
    error_code character varying(64) NOT NULL,
    error_msg character varying(512),
    payload_json jsonb,
    retry_count integer DEFAULT 0 NOT NULL,
    max_retries integer DEFAULT 5 NOT NULL,
    next_retry_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.event_error_log OWNER TO wms;

--
-- Name: event_error_log_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.event_error_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.event_error_log_id_seq OWNER TO wms;

--
-- Name: event_error_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.event_error_log_id_seq OWNED BY public.event_error_log.id;


--
-- Name: event_log; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.event_log (
    id bigint NOT NULL,
    source text NOT NULL,
    level text DEFAULT 'INFO'::text NOT NULL,
    message jsonb NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_event_log_level CHECK ((level = ANY (ARRAY['DEBUG'::text, 'INFO'::text, 'WARN'::text, 'ERROR'::text])))
);


ALTER TABLE public.event_log OWNER TO wms;

--
-- Name: event_log_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.event_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.event_log_id_seq OWNER TO wms;

--
-- Name: event_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.event_log_id_seq OWNED BY public.event_log.id;


--
-- Name: event_replay_cursor_backup_20251109; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.event_replay_cursor_backup_20251109 (
    id bigint NOT NULL,
    platform text NOT NULL,
    last_event_ts timestamp with time zone DEFAULT '1970-01-01 00:00:00+00'::timestamp with time zone NOT NULL
);


ALTER TABLE public.event_replay_cursor_backup_20251109 OWNER TO wms;

--
-- Name: event_replay_cursor_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.event_replay_cursor_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.event_replay_cursor_id_seq OWNER TO wms;

--
-- Name: event_replay_cursor_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.event_replay_cursor_id_seq OWNED BY public.event_replay_cursor_backup_20251109.id;


--
-- Name: event_store; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.event_store (
    id bigint NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    topic character varying(64) NOT NULL,
    key character varying(128),
    payload json NOT NULL,
    headers json,
    status character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text,
    trace_id character varying(64),
    checksum character varying(64)
);


ALTER TABLE public.event_store OWNER TO wms;

--
-- Name: event_store_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.event_store_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.event_store_id_seq OWNER TO wms;

--
-- Name: event_store_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.event_store_id_seq OWNED BY public.event_store.id;


--
-- Name: inventory_movements; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.inventory_movements (
    id text NOT NULL,
    item_id integer NOT NULL,
    location_id integer NOT NULL,
    batch_code character varying(64),
    qty numeric(18,6) NOT NULL,
    reason character varying(32) NOT NULL,
    ref character varying(255),
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    item_sku character varying,
    from_location_id integer,
    to_location_id integer,
    quantity double precision NOT NULL,
    movement_type public.movementtype NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.inventory_movements OWNER TO wms;

--
-- Name: inventory_movements_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.inventory_movements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.inventory_movements_id_seq OWNER TO wms;

--
-- Name: inventory_movements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.inventory_movements_id_seq OWNED BY public.inventory_movements.id;


--
-- Name: item_barcodes; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.item_barcodes (
    id bigint NOT NULL,
    item_id bigint NOT NULL,
    barcode text NOT NULL,
    kind text DEFAULT 'EAN13'::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.item_barcodes OWNER TO wms;

--
-- Name: COLUMN item_barcodes.kind; Type: COMMENT; Schema: public; Owner: wms
--

COMMENT ON COLUMN public.item_barcodes.kind IS 'EAN13 / UPC / INNER / CUSTOM ...';


--
-- Name: item_barcodes_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.item_barcodes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.item_barcodes_id_seq OWNER TO wms;

--
-- Name: item_barcodes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.item_barcodes_id_seq OWNED BY public.item_barcodes.id;


--
-- Name: items; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.items (
    id integer NOT NULL,
    sku character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    qty_available integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    unit character varying(8) DEFAULT 'PCS'::character varying NOT NULL,
    shelf_life_days integer
);


ALTER TABLE public.items OWNER TO wms;

--
-- Name: items_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.items_id_seq OWNER TO wms;

--
-- Name: items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.items_id_seq OWNED BY public.items.id;


--
-- Name: locations; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.locations (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    warehouse_id integer NOT NULL,
    code text NOT NULL,
    current_item_id integer,
    current_batch_id integer
);


ALTER TABLE public.locations OWNER TO wms;

--
-- Name: locations_backup_20251110; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.locations_backup_20251110 (
    id integer,
    name character varying(100),
    warehouse_id integer,
    code text
);


ALTER TABLE public.locations_backup_20251110 OWNER TO wms;

--
-- Name: locations_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.locations_id_seq OWNER TO wms;

--
-- Name: locations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.locations_id_seq OWNED BY public.locations.id;


--
-- Name: order_address_backup_20251109; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.order_address_backup_20251109 (
    order_id bigint NOT NULL,
    receiver_name character varying(255),
    receiver_phone character varying(64),
    province character varying(64),
    city character varying(64),
    district character varying(64),
    detail character varying(512),
    zipcode character varying(32)
);


ALTER TABLE public.order_address_backup_20251109 OWNER TO wms;

--
-- Name: order_items; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.order_items (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    item_id integer NOT NULL,
    qty integer NOT NULL,
    unit_price numeric(10,2),
    line_amount numeric(12,2),
    sku_id character varying(128),
    title character varying(255),
    price numeric(12,2) DEFAULT 0.00 NOT NULL,
    discount numeric(12,2) DEFAULT 0.00 NOT NULL,
    amount numeric(12,2) DEFAULT 0.00 NOT NULL,
    extras jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT chk_order_items_amount_nonneg CHECK (((price >= (0)::numeric) AND (discount >= (0)::numeric) AND (amount >= (0)::numeric))),
    CONSTRAINT chk_order_items_qty_pos CHECK ((qty > 0)),
    CONSTRAINT ck_order_items_line_amount_nonneg CHECK ((line_amount >= (0)::numeric)),
    CONSTRAINT ck_order_items_qty_nonneg CHECK ((qty >= 0)),
    CONSTRAINT ck_order_items_unit_price_nonneg CHECK ((unit_price >= (0)::numeric))
);


ALTER TABLE public.order_items OWNER TO wms;

--
-- Name: order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_items_id_seq OWNER TO wms;

--
-- Name: order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.order_items_id_seq OWNED BY public.order_items.id;


--
-- Name: order_lines; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.order_lines (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    item_id bigint NOT NULL,
    req_qty integer NOT NULL
);


ALTER TABLE public.order_lines OWNER TO wms;

--
-- Name: order_lines_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.order_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_lines_id_seq OWNER TO wms;

--
-- Name: order_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.order_lines_id_seq OWNED BY public.order_lines.id;


--
-- Name: order_logistics; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.order_logistics (
    id integer NOT NULL,
    order_id bigint NOT NULL,
    carrier_code character varying(64),
    carrier_name character varying(128),
    tracking_no character varying(128),
    status character varying(32),
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    carrier character varying(64),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.order_logistics OWNER TO wms;

--
-- Name: order_logistics_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.order_logistics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_logistics_id_seq OWNER TO wms;

--
-- Name: order_logistics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.order_logistics_id_seq OWNED BY public.order_logistics.id;


--
-- Name: order_state_snapshot; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.order_state_snapshot (
    id bigint NOT NULL,
    platform character varying(32) NOT NULL,
    shop_id character varying(64) NOT NULL,
    order_no character varying(128) NOT NULL,
    state character varying(32) NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.order_state_snapshot OWNER TO wms;

--
-- Name: order_state_snapshot_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.order_state_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_state_snapshot_id_seq OWNER TO wms;

--
-- Name: order_state_snapshot_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.order_state_snapshot_id_seq OWNED BY public.order_state_snapshot.id;


--
-- Name: orders; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.orders (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    order_no character varying(64),
    order_type character varying(32),
    status character varying(32) DEFAULT 'CREATED'::character varying NOT NULL,
    customer_name character varying(128),
    supplier_name character varying(128),
    total_amount numeric(12,2) DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    buyer_name character varying(255),
    buyer_phone character varying(64),
    order_amount numeric(12,2) DEFAULT 0.00 NOT NULL,
    pay_amount numeric(12,2) DEFAULT 0.00 NOT NULL,
    CONSTRAINT chk_orders_amount_nonneg CHECK (((order_amount >= (0)::numeric) AND (pay_amount >= (0)::numeric)))
);


ALTER TABLE public.orders OWNER TO wms;

--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.orders_id_seq OWNER TO wms;

--
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;


--
-- Name: outbound_commits; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.outbound_commits (
    id integer NOT NULL,
    ref character varying(64) NOT NULL,
    item_id integer NOT NULL,
    location_id integer NOT NULL,
    qty integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    platform character varying(32),
    state character varying(32),
    shop_id character varying(64) DEFAULT ''::character varying NOT NULL
);


ALTER TABLE public.outbound_commits OWNER TO wms;

--
-- Name: outbound_commits_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.outbound_commits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.outbound_commits_id_seq OWNER TO wms;

--
-- Name: outbound_commits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.outbound_commits_id_seq OWNED BY public.outbound_commits.id;


--
-- Name: outbound_ship_ops; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.outbound_ship_ops (
    id integer NOT NULL,
    store_id integer NOT NULL,
    ref character varying(128) NOT NULL,
    item_id integer NOT NULL,
    location_id integer NOT NULL,
    qty integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.outbound_ship_ops OWNER TO wms;

--
-- Name: outbound_ship_ops_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.outbound_ship_ops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.outbound_ship_ops_id_seq OWNER TO wms;

--
-- Name: outbound_ship_ops_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.outbound_ship_ops_id_seq OWNED BY public.outbound_ship_ops.id;


--
-- Name: pick_task_line_reservations_backup_20251109; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.pick_task_line_reservations_backup_20251109 (
    id bigint NOT NULL,
    task_line_id bigint NOT NULL,
    reservation_id bigint NOT NULL,
    qty bigint NOT NULL,
    CONSTRAINT pick_task_line_reservations_qty_check CHECK ((qty > 0))
);


ALTER TABLE public.pick_task_line_reservations_backup_20251109 OWNER TO wms;

--
-- Name: pick_task_line_reservations_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.pick_task_line_reservations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pick_task_line_reservations_id_seq OWNER TO wms;

--
-- Name: pick_task_line_reservations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.pick_task_line_reservations_id_seq OWNED BY public.pick_task_line_reservations_backup_20251109.id;


--
-- Name: pick_task_lines; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.pick_task_lines (
    id bigint NOT NULL,
    task_id bigint NOT NULL,
    order_id bigint,
    order_line_id bigint,
    item_id bigint NOT NULL,
    req_qty bigint NOT NULL,
    picked_qty bigint DEFAULT 0 NOT NULL,
    status text DEFAULT 'OPEN'::text NOT NULL,
    prefer_pickface boolean DEFAULT true NOT NULL,
    target_location_id bigint,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_pick_task_lines_status CHECK ((status = ANY (ARRAY['OPEN'::text, 'PARTIAL'::text, 'DONE'::text, 'CANCELLED'::text]))),
    CONSTRAINT pick_task_lines_check CHECK ((picked_qty <= req_qty)),
    CONSTRAINT pick_task_lines_picked_qty_check CHECK ((picked_qty >= 0)),
    CONSTRAINT pick_task_lines_req_qty_check CHECK ((req_qty > 0))
);


ALTER TABLE public.pick_task_lines OWNER TO wms;

--
-- Name: pick_task_lines_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.pick_task_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pick_task_lines_id_seq OWNER TO wms;

--
-- Name: pick_task_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.pick_task_lines_id_seq OWNED BY public.pick_task_lines.id;


--
-- Name: pick_tasks; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.pick_tasks (
    id bigint NOT NULL,
    ref text,
    warehouse_id bigint NOT NULL,
    source text DEFAULT 'SYSTEM'::text NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    status text DEFAULT 'READY'::text NOT NULL,
    assigned_to text,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_pick_tasks_status CHECK ((status = ANY (ARRAY['READY'::text, 'ASSIGNED'::text, 'PICKING'::text, 'DONE'::text, 'CANCELLED'::text])))
);


ALTER TABLE public.pick_tasks OWNER TO wms;

--
-- Name: pick_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.pick_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pick_tasks_id_seq OWNER TO wms;

--
-- Name: pick_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.pick_tasks_id_seq OWNED BY public.pick_tasks.id;


--
-- Name: platform_events; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.platform_events (
    id integer NOT NULL,
    platform text NOT NULL,
    event_type text NOT NULL,
    event_id text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    payload jsonb NOT NULL,
    status text DEFAULT 'NEW'::text NOT NULL,
    dedup_key text GENERATED ALWAYS AS (((((platform || ':'::text) || event_type) || ':'::text) || event_id)) STORED,
    shop_id text NOT NULL,
    CONSTRAINT ck_platform_events_status CHECK ((status = ANY (ARRAY['NEW'::text, 'NORMALIZED'::text, 'DISPATCHED'::text, 'PERSISTED'::text, 'ERROR'::text])))
);


ALTER TABLE public.platform_events OWNER TO wms;

--
-- Name: platform_events_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.platform_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.platform_events_id_seq OWNER TO wms;

--
-- Name: platform_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.platform_events_id_seq OWNED BY public.platform_events.id;


--
-- Name: platform_shops; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.platform_shops (
    id bigint NOT NULL,
    platform character varying(32) NOT NULL,
    shop_id character varying(64) NOT NULL,
    access_token text,
    refresh_token text,
    token_expires_at timestamp with time zone,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    rate_limit_qps integer DEFAULT 5,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.platform_shops OWNER TO wms;

--
-- Name: platform_shops_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.platform_shops_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.platform_shops_id_seq OWNER TO wms;

--
-- Name: platform_shops_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.platform_shops_id_seq OWNED BY public.platform_shops.id;


--
-- Name: reservation_allocations; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.reservation_allocations (
    id bigint NOT NULL,
    reservation_id bigint NOT NULL,
    item_id bigint NOT NULL,
    warehouse_id bigint NOT NULL,
    location_id bigint NOT NULL,
    batch_id bigint,
    qty numeric(18,6) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_resalloc_qty_positive CHECK ((qty > (0)::numeric))
);


ALTER TABLE public.reservation_allocations OWNER TO wms;

--
-- Name: reservation_allocations_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.reservation_allocations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reservation_allocations_id_seq OWNER TO wms;

--
-- Name: reservation_allocations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.reservation_allocations_id_seq OWNED BY public.reservation_allocations.id;


--
-- Name: reservation_lines; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.reservation_lines (
    id bigint NOT NULL,
    reservation_id bigint NOT NULL,
    ref_line integer NOT NULL,
    item_id integer NOT NULL,
    qty integer NOT NULL,
    batch_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.reservation_lines OWNER TO wms;

--
-- Name: reservation_lines_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.reservation_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reservation_lines_id_seq OWNER TO wms;

--
-- Name: reservation_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.reservation_lines_id_seq OWNED BY public.reservation_lines.id;


--
-- Name: reservations; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.reservations (
    id bigint NOT NULL,
    item_id integer,
    location_id integer,
    qty integer DEFAULT 0,
    status text DEFAULT 'PLANNED'::text NOT NULL,
    ref text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    order_id bigint,
    batch_id bigint,
    platform character varying(32) NOT NULL,
    shop_id character varying(128) NOT NULL,
    warehouse_id integer NOT NULL,
    locked_qty integer DEFAULT 0 NOT NULL,
    released_at timestamp with time zone
);


ALTER TABLE public.reservations OWNER TO wms;

--
-- Name: reservations_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.reservations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reservations_id_seq OWNER TO wms;

--
-- Name: reservations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.reservations_id_seq OWNED BY public.reservations.id;


--
-- Name: snapshots; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.snapshots (
    id bigint NOT NULL,
    snapshot_date date NOT NULL,
    warehouse_id integer NOT NULL,
    item_id integer NOT NULL,
    batch_code character varying(64) NOT NULL,
    qty_on_hand integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.snapshots OWNER TO wms;

--
-- Name: snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.snapshots_id_seq OWNER TO wms;

--
-- Name: snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.snapshots_id_seq OWNED BY public.snapshots.id;


--
-- Name: stock_ledger; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.stock_ledger (
    id integer NOT NULL,
    stock_id integer,
    reason character varying(32) NOT NULL,
    after_qty integer NOT NULL,
    delta integer NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    ref character varying(128) NOT NULL,
    ref_line integer DEFAULT 1 NOT NULL,
    item_id integer NOT NULL,
    warehouse_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    batch_code character varying(64) NOT NULL,
    CONSTRAINT ck_ledger_delta_nonzero CHECK (((delta)::double precision <> ((0)::numeric)::double precision))
);


ALTER TABLE public.stock_ledger OWNER TO wms;

--
-- Name: stock_ledger_backup_20251110; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.stock_ledger_backup_20251110 (
    id integer,
    stock_id integer,
    reason character varying(32),
    after_qty double precision,
    delta double precision,
    occurred_at timestamp with time zone,
    ref character varying(128),
    ref_line integer,
    item_id integer,
    location_id integer,
    warehouse_id integer,
    created_at timestamp with time zone
);


ALTER TABLE public.stock_ledger_backup_20251110 OWNER TO wms;

--
-- Name: stock_ledger_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.stock_ledger_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_ledger_id_seq OWNER TO wms;

--
-- Name: stock_ledger_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.stock_ledger_id_seq OWNED BY public.stock_ledger.id;


--
-- Name: stock_snapshots; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.stock_snapshots (
    id bigint NOT NULL,
    as_of_ts timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    item_id bigint NOT NULL,
    location_id bigint NOT NULL,
    qty numeric(18,4) DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    snapshot_date date NOT NULL,
    qty_on_hand integer NOT NULL,
    qty_available integer NOT NULL,
    warehouse_id integer,
    updated_at timestamp with time zone,
    batch_id integer,
    qty_allocated integer NOT NULL,
    expiry_date date,
    age_days integer
);


ALTER TABLE public.stock_snapshots OWNER TO wms;

--
-- Name: stock_snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.stock_snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_snapshots_id_seq OWNER TO wms;

--
-- Name: stock_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.stock_snapshots_id_seq OWNED BY public.stock_snapshots.id;


--
-- Name: stocks; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.stocks (
    id integer NOT NULL,
    item_id integer NOT NULL,
    qty_on_hand integer DEFAULT 0 NOT NULL,
    batch_id integer,
    warehouse_id integer NOT NULL,
    batch_code character varying(64) NOT NULL,
    qty integer NOT NULL
);


ALTER TABLE public.stocks OWNER TO wms;

--
-- Name: stocks_backup_20251110; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.stocks_backup_20251110 (
    id integer,
    item_id integer,
    location_id integer,
    qty integer,
    batch_id integer
);


ALTER TABLE public.stocks_backup_20251110 OWNER TO wms;

--
-- Name: stocks_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.stocks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stocks_id_seq OWNER TO wms;

--
-- Name: stocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.stocks_id_seq OWNED BY public.stocks.id;


--
-- Name: store_items; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.store_items (
    id integer NOT NULL,
    store_id integer NOT NULL,
    item_id integer NOT NULL,
    pdd_sku_id character varying(64),
    outer_id character varying(128)
);


ALTER TABLE public.store_items OWNER TO wms;

--
-- Name: store_items_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.store_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.store_items_id_seq OWNER TO wms;

--
-- Name: store_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.store_items_id_seq OWNED BY public.store_items.id;


--
-- Name: store_warehouse; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.store_warehouse (
    id bigint NOT NULL,
    store_id bigint NOT NULL,
    warehouse_id bigint NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.store_warehouse OWNER TO wms;

--
-- Name: store_warehouse_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.store_warehouse_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.store_warehouse_id_seq OWNER TO wms;

--
-- Name: store_warehouse_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.store_warehouse_id_seq OWNED BY public.store_warehouse.id;


--
-- Name: stores; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.stores (
    id integer NOT NULL,
    name character varying(128) NOT NULL,
    platform character varying(16) DEFAULT 'pdd'::character varying NOT NULL,
    api_token bytea,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    app_key character varying(128),
    app_secret character varying(256),
    callback_url character varying(256),
    shop_id character varying(128)
);


ALTER TABLE public.stores OWNER TO wms;

--
-- Name: stores_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.stores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stores_id_seq OWNER TO wms;

--
-- Name: stores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.stores_id_seq OWNED BY public.stores.id;


--
-- Name: warehouses; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.warehouses (
    id integer NOT NULL,
    name character varying(100) NOT NULL
);


ALTER TABLE public.warehouses OWNER TO wms;

--
-- Name: v_available; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_available AS
 SELECT s.item_id,
    s.batch_code,
    s.warehouse_id,
    s.qty_on_hand AS qty
   FROM (public.stocks s
     JOIN public.warehouses w ON ((w.id = s.warehouse_id)))
  WHERE ((w.name)::text = 'MAIN'::text);


ALTER VIEW public.v_available OWNER TO wms;

--
-- Name: v_event_errors_pending; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_event_errors_pending AS
 SELECT e.id,
    e.dedup_key,
    e.stage,
    e.error,
    e.occurred_at,
    (e.meta ->> 'platform'::text) AS platform,
    (e.meta ->> 'shop_id'::text) AS shop_id,
    (e.meta ->> 'order_no'::text) AS order_no,
    (e.meta ->> 'event_id'::text) AS event_id,
    (e.meta ->> 'error_code'::text) AS error_code,
    (e.meta ->> 'error_type'::text) AS error_type,
    (e.meta ->> 'error_msg'::text) AS error_msg,
    (e.meta ->> 'message'::text) AS message,
    (e.meta ->> 'idempotency_key'::text) AS idempotency_key,
    (e.meta ->> 'from_state'::text) AS from_state,
    (e.meta ->> 'to_state'::text) AS to_state,
    ((e.meta ->> 'next_retry_at'::text))::timestamp with time zone AS next_retry_at,
    ((e.meta ->> 'retry_count'::text))::integer AS retry_count,
    ((e.meta ->> 'max_retries'::text))::integer AS max_retries,
    COALESCE((e.meta -> 'payload'::text), (e.meta -> 'payload_json'::text)) AS payload
   FROM public.event_error_log e
  WHERE (e.stage = ANY (ARRAY['ingest'::text, 'dispatch'::text]));


ALTER VIEW public.v_event_errors_pending OWNER TO wms;

--
-- Name: v_onhand; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_onhand AS
 SELECT s.item_id,
    s.batch_code,
    sum(s.qty_on_hand) AS qty
   FROM public.stocks s
  GROUP BY s.item_id, s.batch_code;


ALTER VIEW public.v_onhand OWNER TO wms;

--
-- Name: v_returns_pool; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_returns_pool AS
 SELECT s.item_id,
    s.batch_code,
    s.qty_on_hand
   FROM (public.stocks s
     JOIN public.warehouses w ON ((w.id = s.warehouse_id)))
  WHERE ((w.name)::text = 'RETURNS'::text);


ALTER VIEW public.v_returns_pool OWNER TO wms;

--
-- Name: v_scan_errors_recent; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_scan_errors_recent AS
 SELECT event_error_log.id,
    event_error_log.occurred_at,
    event_error_log.dedup_key,
    event_error_log.stage,
    COALESCE(event_error_log.error, (event_error_log.meta ->> 'error_msg'::text), ''::text) AS error_msg,
    event_error_log.meta
   FROM public.event_error_log
  WHERE ((event_error_log.stage = 'ingest'::text) AND (event_error_log.occurred_at >= (now() - '00:10:00'::interval)))
  ORDER BY event_error_log.id DESC;


ALTER VIEW public.v_scan_errors_recent OWNER TO wms;

--
-- Name: v_scan_recent; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_scan_recent AS
 SELECT e.id AS event_id,
    e.source,
    e.occurred_at,
    e.message AS message_raw,
    COALESCE((e.message ->> 'ref'::text), (e.message ->> 'scan_ref'::text), btrim((e.message)::text, '"'::text)) AS scan_ref
   FROM public.event_log e
  WHERE (e.source ~~ 'scan_%'::text)
  ORDER BY e.occurred_at DESC
 LIMIT 500;


ALTER VIEW public.v_scan_recent OWNER TO wms;

--
-- Name: v_snapshot_totals; Type: VIEW; Schema: public; Owner: wms
--

CREATE VIEW public.v_snapshot_totals AS
 SELECT stock_snapshots.snapshot_date,
    COALESCE(sum(stock_snapshots.qty_on_hand), (0)::bigint) AS sum_on_hand,
    COALESCE(sum(stock_snapshots.qty_available), (0)::bigint) AS sum_available,
    COALESCE(sum(stock_snapshots.qty_allocated), (0)::bigint) AS sum_allocated
   FROM public.stock_snapshots
  GROUP BY stock_snapshots.snapshot_date;


ALTER VIEW public.v_snapshot_totals OWNER TO wms;

--
-- Name: warehouses_id_seq; Type: SEQUENCE; Schema: public; Owner: wms
--

CREATE SEQUENCE public.warehouses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.warehouses_id_seq OWNER TO wms;

--
-- Name: warehouses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wms
--

ALTER SEQUENCE public.warehouses_id_seq OWNED BY public.warehouses.id;


--
-- Name: audit_events id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.audit_events ALTER COLUMN id SET DEFAULT nextval('public.audit_events_id_seq'::regclass);


--
-- Name: batches id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.batches ALTER COLUMN id SET DEFAULT nextval('public.batches_id_seq'::regclass);


--
-- Name: channel_inventory id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_inventory ALTER COLUMN id SET DEFAULT nextval('public.channel_inventory_id_seq'::regclass);


--
-- Name: channel_reserve_ops_backup_20251109 id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_reserve_ops_backup_20251109 ALTER COLUMN id SET DEFAULT nextval('public.channel_reserve_ops_id_seq'::regclass);


--
-- Name: event_error_log id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_error_log ALTER COLUMN id SET DEFAULT nextval('public.event_error_log_id_seq'::regclass);


--
-- Name: event_log id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_log ALTER COLUMN id SET DEFAULT nextval('public.event_log_id_seq'::regclass);


--
-- Name: event_replay_cursor_backup_20251109 id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_replay_cursor_backup_20251109 ALTER COLUMN id SET DEFAULT nextval('public.event_replay_cursor_id_seq'::regclass);


--
-- Name: event_store id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_store ALTER COLUMN id SET DEFAULT nextval('public.event_store_id_seq'::regclass);


--
-- Name: inventory_movements id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.inventory_movements ALTER COLUMN id SET DEFAULT nextval('public.inventory_movements_id_seq'::regclass);


--
-- Name: item_barcodes id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.item_barcodes ALTER COLUMN id SET DEFAULT nextval('public.item_barcodes_id_seq'::regclass);


--
-- Name: items id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.items ALTER COLUMN id SET DEFAULT nextval('public.items_id_seq'::regclass);


--
-- Name: locations id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.locations ALTER COLUMN id SET DEFAULT nextval('public.locations_id_seq'::regclass);


--
-- Name: order_items id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_items ALTER COLUMN id SET DEFAULT nextval('public.order_items_id_seq'::regclass);


--
-- Name: order_lines id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_lines ALTER COLUMN id SET DEFAULT nextval('public.order_lines_id_seq'::regclass);


--
-- Name: order_logistics id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_logistics ALTER COLUMN id SET DEFAULT nextval('public.order_logistics_id_seq'::regclass);


--
-- Name: order_state_snapshot id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_state_snapshot ALTER COLUMN id SET DEFAULT nextval('public.order_state_snapshot_id_seq'::regclass);


--
-- Name: orders id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);


--
-- Name: outbound_commits id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.outbound_commits ALTER COLUMN id SET DEFAULT nextval('public.outbound_commits_id_seq'::regclass);


--
-- Name: outbound_ship_ops id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.outbound_ship_ops ALTER COLUMN id SET DEFAULT nextval('public.outbound_ship_ops_id_seq'::regclass);


--
-- Name: pick_task_line_reservations_backup_20251109 id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_line_reservations_backup_20251109 ALTER COLUMN id SET DEFAULT nextval('public.pick_task_line_reservations_id_seq'::regclass);


--
-- Name: pick_task_lines id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_lines ALTER COLUMN id SET DEFAULT nextval('public.pick_task_lines_id_seq'::regclass);


--
-- Name: pick_tasks id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_tasks ALTER COLUMN id SET DEFAULT nextval('public.pick_tasks_id_seq'::regclass);


--
-- Name: platform_events id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.platform_events ALTER COLUMN id SET DEFAULT nextval('public.platform_events_id_seq'::regclass);


--
-- Name: platform_shops id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.platform_shops ALTER COLUMN id SET DEFAULT nextval('public.platform_shops_id_seq'::regclass);


--
-- Name: reservation_allocations id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_allocations ALTER COLUMN id SET DEFAULT nextval('public.reservation_allocations_id_seq'::regclass);


--
-- Name: reservation_lines id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_lines ALTER COLUMN id SET DEFAULT nextval('public.reservation_lines_id_seq'::regclass);


--
-- Name: reservations id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservations ALTER COLUMN id SET DEFAULT nextval('public.reservations_id_seq'::regclass);


--
-- Name: snapshots id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.snapshots ALTER COLUMN id SET DEFAULT nextval('public.snapshots_id_seq'::regclass);


--
-- Name: stock_ledger id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_ledger ALTER COLUMN id SET DEFAULT nextval('public.stock_ledger_id_seq'::regclass);


--
-- Name: stock_snapshots id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_snapshots ALTER COLUMN id SET DEFAULT nextval('public.stock_snapshots_id_seq'::regclass);


--
-- Name: stocks id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stocks ALTER COLUMN id SET DEFAULT nextval('public.stocks_id_seq'::regclass);


--
-- Name: store_items id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_items ALTER COLUMN id SET DEFAULT nextval('public.store_items_id_seq'::regclass);


--
-- Name: store_warehouse id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_warehouse ALTER COLUMN id SET DEFAULT nextval('public.store_warehouse_id_seq'::regclass);


--
-- Name: stores id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stores ALTER COLUMN id SET DEFAULT nextval('public.stores_id_seq'::regclass);


--
-- Name: warehouses id; Type: DEFAULT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.warehouses ALTER COLUMN id SET DEFAULT nextval('public.warehouses_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);


--
-- Name: batches batches_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.batches
    ADD CONSTRAINT batches_pkey PRIMARY KEY (id);


--
-- Name: channel_inventory channel_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_inventory
    ADD CONSTRAINT channel_inventory_pkey PRIMARY KEY (id);


--
-- Name: channel_reserve_ops_backup_20251109 channel_reserve_ops_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_reserve_ops_backup_20251109
    ADD CONSTRAINT channel_reserve_ops_pkey PRIMARY KEY (id);


--
-- Name: channel_reserved_idem_backup_20251109 channel_reserved_idem_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_reserved_idem_backup_20251109
    ADD CONSTRAINT channel_reserved_idem_pkey PRIMARY KEY (ref);


--
-- Name: event_error_log event_error_log_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_error_log
    ADD CONSTRAINT event_error_log_pkey PRIMARY KEY (id);


--
-- Name: event_log event_log_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_log
    ADD CONSTRAINT event_log_pkey PRIMARY KEY (id);


--
-- Name: event_replay_cursor_backup_20251109 event_replay_cursor_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_replay_cursor_backup_20251109
    ADD CONSTRAINT event_replay_cursor_pkey PRIMARY KEY (id);


--
-- Name: event_replay_cursor_backup_20251109 event_replay_cursor_platform_key; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_replay_cursor_backup_20251109
    ADD CONSTRAINT event_replay_cursor_platform_key UNIQUE (platform);


--
-- Name: event_store event_store_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.event_store
    ADD CONSTRAINT event_store_pkey PRIMARY KEY (id);


--
-- Name: inventory_movements inventory_movements_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_pkey PRIMARY KEY (id);


--
-- Name: item_barcodes item_barcodes_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.item_barcodes
    ADD CONSTRAINT item_barcodes_pkey PRIMARY KEY (id);


--
-- Name: items items_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_pkey PRIMARY KEY (id);


--
-- Name: items items_sku_key; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_sku_key UNIQUE (sku);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (id);


--
-- Name: order_address_backup_20251109 order_address_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_address_backup_20251109
    ADD CONSTRAINT order_address_pkey PRIMARY KEY (order_id);


--
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);


--
-- Name: order_lines order_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_lines
    ADD CONSTRAINT order_lines_pkey PRIMARY KEY (id);


--
-- Name: order_logistics order_logistics_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_logistics
    ADD CONSTRAINT order_logistics_pkey PRIMARY KEY (id);


--
-- Name: order_state_snapshot order_state_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_state_snapshot
    ADD CONSTRAINT order_state_snapshot_pkey PRIMARY KEY (id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: outbound_commits outbound_commits_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.outbound_commits
    ADD CONSTRAINT outbound_commits_pkey PRIMARY KEY (id);


--
-- Name: outbound_ship_ops outbound_ship_ops_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.outbound_ship_ops
    ADD CONSTRAINT outbound_ship_ops_pkey PRIMARY KEY (id);


--
-- Name: pick_task_line_reservations_backup_20251109 pick_task_line_reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_line_reservations_backup_20251109
    ADD CONSTRAINT pick_task_line_reservations_pkey PRIMARY KEY (id);


--
-- Name: pick_task_line_reservations_backup_20251109 pick_task_line_reservations_task_line_id_reservation_id_key; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_line_reservations_backup_20251109
    ADD CONSTRAINT pick_task_line_reservations_task_line_id_reservation_id_key UNIQUE (task_line_id, reservation_id);


--
-- Name: pick_task_lines pick_task_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_lines
    ADD CONSTRAINT pick_task_lines_pkey PRIMARY KEY (id);


--
-- Name: pick_tasks pick_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_tasks
    ADD CONSTRAINT pick_tasks_pkey PRIMARY KEY (id);


--
-- Name: platform_events platform_events_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.platform_events
    ADD CONSTRAINT platform_events_pkey PRIMARY KEY (id);


--
-- Name: platform_shops platform_shops_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.platform_shops
    ADD CONSTRAINT platform_shops_pkey PRIMARY KEY (id);


--
-- Name: reservation_allocations reservation_allocations_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_allocations
    ADD CONSTRAINT reservation_allocations_pkey PRIMARY KEY (id);


--
-- Name: reservation_lines reservation_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_lines
    ADD CONSTRAINT reservation_lines_pkey PRIMARY KEY (id);


--
-- Name: reservations reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_pkey PRIMARY KEY (id);


--
-- Name: snapshots snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT snapshots_pkey PRIMARY KEY (id);


--
-- Name: stock_ledger stock_ledger_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_ledger
    ADD CONSTRAINT stock_ledger_pkey PRIMARY KEY (id);


--
-- Name: stock_snapshots stock_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_snapshots
    ADD CONSTRAINT stock_snapshots_pkey PRIMARY KEY (id);


--
-- Name: stocks stocks_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_pkey PRIMARY KEY (id);


--
-- Name: store_items store_items_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT store_items_pkey PRIMARY KEY (id);


--
-- Name: store_warehouse store_warehouse_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_warehouse
    ADD CONSTRAINT store_warehouse_pkey PRIMARY KEY (id);


--
-- Name: stores stores_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stores
    ADD CONSTRAINT stores_pkey PRIMARY KEY (id);


--
-- Name: batches uq_batches_item_code; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.batches
    ADD CONSTRAINT uq_batches_item_code UNIQUE (item_id, batch_code);


--
-- Name: channel_inventory uq_channel_inventory_store_item; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_inventory
    ADD CONSTRAINT uq_channel_inventory_store_item UNIQUE (store_id, item_id);


--
-- Name: inventory_movements uq_inv_mov_idem_reason_ref_target; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT uq_inv_mov_idem_reason_ref_target UNIQUE (reason, ref, item_id, location_id, batch_code);


--
-- Name: item_barcodes uq_item_barcodes_barcode; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.item_barcodes
    ADD CONSTRAINT uq_item_barcodes_barcode UNIQUE (barcode);


--
-- Name: stock_ledger uq_ledger_idem_reason_refline_item_code_wh; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_ledger
    ADD CONSTRAINT uq_ledger_idem_reason_refline_item_code_wh UNIQUE (reason, ref, ref_line, item_id, batch_code, warehouse_id);


--
-- Name: stock_ledger uq_ledger_wh_batch_item_reason_ref_line; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_ledger
    ADD CONSTRAINT uq_ledger_wh_batch_item_reason_ref_line UNIQUE (warehouse_id, batch_code, item_id, reason, ref, ref_line);


--
-- Name: locations uq_locations_wh_code; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT uq_locations_wh_code UNIQUE (warehouse_id, code);


--
-- Name: channel_reserve_ops_backup_20251109 uq_reserve_idem_key; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_reserve_ops_backup_20251109
    ADD CONSTRAINT uq_reserve_idem_key UNIQUE (store_id, ext_order_id, ext_sku_id, op);


--
-- Name: outbound_ship_ops uq_ship_idem_key; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.outbound_ship_ops
    ADD CONSTRAINT uq_ship_idem_key UNIQUE (store_id, ref, item_id, location_id);


--
-- Name: snapshots uq_snapshots_date_wh_item_code; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT uq_snapshots_date_wh_item_code UNIQUE (snapshot_date, warehouse_id, item_id, batch_code);


--
-- Name: stock_snapshots uq_stock_snapshot_grain; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_snapshots
    ADD CONSTRAINT uq_stock_snapshot_grain UNIQUE (snapshot_date, warehouse_id, location_id, item_id);


--
-- Name: stocks uq_stocks_item_wh_batch; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT uq_stocks_item_wh_batch UNIQUE (item_id, warehouse_id, batch_code);


--
-- Name: store_items uq_store_items_store_item; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT uq_store_items_store_item UNIQUE (store_id, item_id);


--
-- Name: store_items uq_store_items_store_pddsku; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT uq_store_items_store_pddsku UNIQUE (store_id, pdd_sku_id);


--
-- Name: store_warehouse uq_store_wh_unique; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_warehouse
    ADD CONSTRAINT uq_store_wh_unique UNIQUE (store_id, warehouse_id);


--
-- Name: stores uq_stores_platform_shop; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stores
    ADD CONSTRAINT uq_stores_platform_shop UNIQUE (platform, shop_id);


--
-- Name: warehouses warehouses_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.warehouses
    ADD CONSTRAINT warehouses_pkey PRIMARY KEY (id);


--
-- Name: idx_stock_ledger_occurred_at; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX idx_stock_ledger_occurred_at ON public.stock_ledger USING btree (occurred_at);


--
-- Name: idx_stock_ledger_stock_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX idx_stock_ledger_stock_id ON public.stock_ledger USING btree (stock_id);


--
-- Name: ix_audit_events_cat_ref_time; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_audit_events_cat_ref_time ON public.audit_events USING btree (category, ref, created_at);


--
-- Name: ix_audit_events_category; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_audit_events_category ON public.audit_events USING btree (category);


--
-- Name: ix_audit_events_outbound_ref_time; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_audit_events_outbound_ref_time ON public.audit_events USING btree (ref, created_at);


--
-- Name: ix_audit_events_ref; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_audit_events_ref ON public.audit_events USING btree (ref);


--
-- Name: ix_batches_batch_code; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_batches_batch_code ON public.batches USING btree (batch_code);


--
-- Name: ix_batches_expiry_date; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_batches_expiry_date ON public.batches USING btree (expiry_date);


--
-- Name: ix_batches_item_code; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_batches_item_code ON public.batches USING btree (item_id, batch_code);


--
-- Name: ix_batches_item_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_batches_item_id ON public.batches USING btree (item_id);


--
-- Name: ix_batches_production_date; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_batches_production_date ON public.batches USING btree (production_date);


--
-- Name: ix_channel_inventory_item; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_channel_inventory_item ON public.channel_inventory USING btree (item_id);


--
-- Name: ix_channel_inventory_store; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_channel_inventory_store ON public.channel_inventory USING btree (store_id);


--
-- Name: ix_event_error_log_key; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_event_error_log_key ON public.event_error_log USING btree (platform, shop_id, idempotency_key);


--
-- Name: ix_event_error_log_retry; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_event_error_log_retry ON public.event_error_log USING btree (next_retry_at);


--
-- Name: ix_inventory_movements_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_inventory_movements_id ON public.inventory_movements USING btree (id);


--
-- Name: ix_inventory_movements_item_sku; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_inventory_movements_item_sku ON public.inventory_movements USING btree (item_sku);


--
-- Name: ix_inventory_movements_movement_type; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_inventory_movements_movement_type ON public.inventory_movements USING btree (movement_type);


--
-- Name: ix_inventory_movements_sku_time; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_inventory_movements_sku_time ON public.inventory_movements USING btree (item_sku, "timestamp");


--
-- Name: ix_inventory_movements_type_time; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_inventory_movements_type_time ON public.inventory_movements USING btree (movement_type, "timestamp");


--
-- Name: ix_ledger_dims; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_ledger_dims ON public.stock_ledger USING btree (item_id, batch_code, warehouse_id);


--
-- Name: ix_ledger_occurred_at; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_ledger_occurred_at ON public.stock_ledger USING btree (occurred_at);


--
-- Name: ix_locations_current_batch; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_locations_current_batch ON public.locations USING btree (current_batch_id);


--
-- Name: ix_locations_current_item; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_locations_current_item ON public.locations USING btree (current_item_id);


--
-- Name: ix_order_items_order_item; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_order_items_order_item ON public.order_items USING btree (order_id, item_id);


--
-- Name: ix_order_lines_order_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_order_lines_order_id ON public.order_lines USING btree (order_id);


--
-- Name: ix_order_logistics_ord_trk; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_order_logistics_ord_trk ON public.order_logistics USING btree (order_id, tracking_no);


--
-- Name: ix_order_logistics_order_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_order_logistics_order_id ON public.order_logistics USING btree (order_id);


--
-- Name: ix_order_logistics_tracking_no; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_order_logistics_tracking_no ON public.order_logistics USING btree (tracking_no);


--
-- Name: ix_order_state_snapshot_lookup; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX ix_order_state_snapshot_lookup ON public.order_state_snapshot USING btree (platform, shop_id, order_no);


--
-- Name: ix_platform_shops_status; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_platform_shops_status ON public.platform_shops USING btree (status);


--
-- Name: ix_resalloc_batch; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_resalloc_batch ON public.reservation_allocations USING btree (batch_id);


--
-- Name: ix_resalloc_item_wh_loc; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_resalloc_item_wh_loc ON public.reservation_allocations USING btree (item_id, warehouse_id, location_id);


--
-- Name: ix_resalloc_reservation; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_resalloc_reservation ON public.reservation_allocations USING btree (reservation_id);


--
-- Name: ix_reservation_lines_item; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_reservation_lines_item ON public.reservation_lines USING btree (item_id);


--
-- Name: ix_reservation_lines_ref_line; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_reservation_lines_ref_line ON public.reservation_lines USING btree (ref_line);


--
-- Name: ix_reservation_lines_res_refline; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX ix_reservation_lines_res_refline ON public.reservation_lines USING btree (reservation_id, ref_line);


--
-- Name: ix_reservations_item_loc_active; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_reservations_item_loc_active ON public.reservations USING btree (item_id, location_id) WHERE (status = 'ACTIVE'::text);


--
-- Name: ix_snapshots_batch_code; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_snapshots_batch_code ON public.snapshots USING btree (batch_code);


--
-- Name: ix_snapshots_date; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_snapshots_date ON public.snapshots USING btree (snapshot_date);


--
-- Name: ix_snapshots_wh_item; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_snapshots_wh_item ON public.snapshots USING btree (warehouse_id, item_id);


--
-- Name: ix_stock_ledger_batch_code; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_batch_code ON public.stock_ledger USING btree (batch_code);


--
-- Name: ix_stock_ledger_item_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_item_id ON public.stock_ledger USING btree (item_id);


--
-- Name: ix_stock_ledger_item_time; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_item_time ON public.stock_ledger USING btree (item_id, occurred_at);


--
-- Name: ix_stock_ledger_occurred_at; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_occurred_at ON public.stock_ledger USING btree (occurred_at);


--
-- Name: ix_stock_ledger_ref; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_ref ON public.stock_ledger USING btree (ref);


--
-- Name: ix_stock_ledger_stock_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_stock_id ON public.stock_ledger USING btree (stock_id);


--
-- Name: ix_stock_ledger_warehouse_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stock_ledger_warehouse_id ON public.stock_ledger USING btree (warehouse_id);


--
-- Name: ix_stocks_item_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stocks_item_id ON public.stocks USING btree (item_id);


--
-- Name: ix_stocks_item_wh_batch; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stocks_item_wh_batch ON public.stocks USING btree (item_id, warehouse_id, batch_code);


--
-- Name: ix_stocks_warehouse_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stocks_warehouse_id ON public.stocks USING btree (warehouse_id);


--
-- Name: ix_store_warehouse_store_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_store_warehouse_store_id ON public.store_warehouse USING btree (store_id);


--
-- Name: ix_store_warehouse_warehouse_id; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_store_warehouse_warehouse_id ON public.store_warehouse USING btree (warehouse_id);


--
-- Name: ix_store_wh_store_default; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_store_wh_store_default ON public.store_warehouse USING btree (store_id, is_default, priority);


--
-- Name: ix_stores_platform_active; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stores_platform_active ON public.stores USING btree (platform, active);


--
-- Name: ix_stores_platform_name; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX ix_stores_platform_name ON public.stores USING btree (platform, name);


--
-- Name: uq_resalloc_null_batch; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX uq_resalloc_null_batch ON public.reservation_allocations USING btree (reservation_id, item_id, warehouse_id, location_id) WHERE (batch_id IS NULL);


--
-- Name: uq_resalloc_with_batch; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX uq_resalloc_with_batch ON public.reservation_allocations USING btree (reservation_id, item_id, warehouse_id, location_id, batch_id) WHERE (batch_id IS NOT NULL);


--
-- Name: uq_reserve_idem; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX uq_reserve_idem ON public.reservations USING btree (ref, item_id, location_id) WHERE (status = 'ACTIVE'::text);


--
-- Name: uq_warehouses_name; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX uq_warehouses_name ON public.warehouses USING btree (name);


--
-- Name: batches trg_batches_fill_expire_at; Type: TRIGGER; Schema: public; Owner: wms
--

CREATE TRIGGER trg_batches_fill_expire_at BEFORE INSERT OR UPDATE ON public.batches FOR EACH ROW EXECUTE FUNCTION public.batches_fill_expire_at();


--
-- Name: locations trg_locations_fill_code; Type: TRIGGER; Schema: public; Owner: wms
--

CREATE TRIGGER trg_locations_fill_code BEFORE INSERT ON public.locations FOR EACH ROW EXECUTE FUNCTION public.locations_fill_code();


--
-- Name: pick_task_lines trg_pt_aggregate; Type: TRIGGER; Schema: public; Owner: wms
--

CREATE TRIGGER trg_pt_aggregate AFTER INSERT OR UPDATE OF status, picked_qty, req_qty ON public.pick_task_lines FOR EACH ROW EXECUTE FUNCTION public.pick_tasks_aggregate_status();


--
-- Name: pick_task_lines trg_ptl_autostatus; Type: TRIGGER; Schema: public; Owner: wms
--

CREATE TRIGGER trg_ptl_autostatus BEFORE INSERT OR UPDATE OF picked_qty, req_qty ON public.pick_task_lines FOR EACH ROW EXECUTE FUNCTION public.pick_task_lines_auto_status();


--
-- Name: stocks trg_stocks_qty_sync; Type: TRIGGER; Schema: public; Owner: wms
--

CREATE TRIGGER trg_stocks_qty_sync BEFORE INSERT OR UPDATE ON public.stocks FOR EACH ROW EXECUTE FUNCTION public.stocks_qty_sync();


--
-- Name: stores trg_stores_touch; Type: TRIGGER; Schema: public; Owner: wms
--

CREATE TRIGGER trg_stores_touch BEFORE UPDATE ON public.stores FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();


--
-- Name: channel_inventory channel_inventory_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_inventory
    ADD CONSTRAINT channel_inventory_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id) ON DELETE RESTRICT;


--
-- Name: channel_inventory channel_inventory_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_inventory
    ADD CONSTRAINT channel_inventory_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id) ON DELETE RESTRICT;


--
-- Name: channel_reserve_ops_backup_20251109 channel_reserve_ops_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.channel_reserve_ops_backup_20251109
    ADD CONSTRAINT channel_reserve_ops_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id) ON DELETE RESTRICT;


--
-- Name: batches fk_batches_item; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.batches
    ADD CONSTRAINT fk_batches_item FOREIGN KEY (item_id) REFERENCES public.items(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: locations fk_locations_current_batch; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT fk_locations_current_batch FOREIGN KEY (current_batch_id) REFERENCES public.batches(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;


--
-- Name: locations fk_locations_current_item; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT fk_locations_current_item FOREIGN KEY (current_item_id) REFERENCES public.items(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;


--
-- Name: locations fk_locations_warehouse; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT fk_locations_warehouse FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;


--
-- Name: order_items fk_order_items_item; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT fk_order_items_item FOREIGN KEY (item_id) REFERENCES public.items(id) ON DELETE RESTRICT;


--
-- Name: order_items fk_order_items_item_id_items; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT fk_order_items_item_id_items FOREIGN KEY (item_id) REFERENCES public.items(id) ON DELETE SET NULL;


--
-- Name: order_items fk_order_items_order; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: reservation_allocations fk_resalloc_batch; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_allocations
    ADD CONSTRAINT fk_resalloc_batch FOREIGN KEY (batch_id) REFERENCES public.batches(id) ON DELETE SET NULL;


--
-- Name: reservation_allocations fk_resalloc_reservation; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_allocations
    ADD CONSTRAINT fk_resalloc_reservation FOREIGN KEY (reservation_id) REFERENCES public.reservations(id) ON DELETE CASCADE;


--
-- Name: reservations fk_reservations_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT fk_reservations_batch_id FOREIGN KEY (batch_id) REFERENCES public.batches(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reservations fk_reservations_order_id; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT fk_reservations_order_id FOREIGN KEY (order_id) REFERENCES public.orders(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: snapshots fk_snapshots_item; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT fk_snapshots_item FOREIGN KEY (item_id) REFERENCES public.items(id);


--
-- Name: snapshots fk_snapshots_warehouse; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT fk_snapshots_warehouse FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);


--
-- Name: stock_snapshots fk_ss_batch; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_snapshots
    ADD CONSTRAINT fk_ss_batch FOREIGN KEY (batch_id) REFERENCES public.batches(id) ON DELETE SET NULL;


--
-- Name: stock_ledger fk_stock_ledger_item_id; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stock_ledger
    ADD CONSTRAINT fk_stock_ledger_item_id FOREIGN KEY (item_id) REFERENCES public.items(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: stocks fk_stocks_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT fk_stocks_batch_id FOREIGN KEY (batch_id) REFERENCES public.batches(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;


--
-- Name: stocks fk_stocks_item; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT fk_stocks_item FOREIGN KEY (item_id) REFERENCES public.items(id) ON DELETE RESTRICT;


--
-- Name: stocks fk_stocks_warehouse; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT fk_stocks_warehouse FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;


--
-- Name: inventory_movements inventory_movements_from_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_from_location_id_fkey FOREIGN KEY (from_location_id) REFERENCES public.locations(id);


--
-- Name: inventory_movements inventory_movements_item_sku_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_item_sku_fkey FOREIGN KEY (item_sku) REFERENCES public.items(sku);


--
-- Name: inventory_movements inventory_movements_to_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_to_location_id_fkey FOREIGN KEY (to_location_id) REFERENCES public.locations(id);


--
-- Name: item_barcodes item_barcodes_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.item_barcodes
    ADD CONSTRAINT item_barcodes_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id) ON DELETE CASCADE;


--
-- Name: order_address_backup_20251109 order_address_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_address_backup_20251109
    ADD CONSTRAINT order_address_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_lines order_lines_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_lines
    ADD CONSTRAINT order_lines_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_logistics order_logistics_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.order_logistics
    ADD CONSTRAINT order_logistics_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: outbound_ship_ops outbound_ship_ops_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.outbound_ship_ops
    ADD CONSTRAINT outbound_ship_ops_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id) ON DELETE RESTRICT;


--
-- Name: pick_task_line_reservations_backup_20251109 pick_task_line_reservations_task_line_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_line_reservations_backup_20251109
    ADD CONSTRAINT pick_task_line_reservations_task_line_id_fkey FOREIGN KEY (task_line_id) REFERENCES public.pick_task_lines(id) ON DELETE CASCADE;


--
-- Name: pick_task_lines pick_task_lines_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.pick_task_lines
    ADD CONSTRAINT pick_task_lines_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.pick_tasks(id) ON DELETE CASCADE;


--
-- Name: reservation_lines reservation_lines_reservation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_lines
    ADD CONSTRAINT reservation_lines_reservation_id_fkey FOREIGN KEY (reservation_id) REFERENCES public.reservations(id) ON DELETE CASCADE;


--
-- Name: reservation_lines reservation_lines_reservation_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.reservation_lines
    ADD CONSTRAINT reservation_lines_reservation_id_fkey1 FOREIGN KEY (reservation_id) REFERENCES public.reservations(id);


--
-- Name: store_items store_items_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT store_items_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id) ON DELETE RESTRICT;


--
-- Name: store_items store_items_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT store_items_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id) ON DELETE RESTRICT;


--
-- Name: store_warehouse store_warehouse_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_warehouse
    ADD CONSTRAINT store_warehouse_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id) ON DELETE CASCADE;


--
-- Name: store_warehouse store_warehouse_warehouse_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.store_warehouse
    ADD CONSTRAINT store_warehouse_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE CASCADE;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: wms
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict H7LcAr3giEU4f23SDDhEgtjlFexXHZoEmhCQtItj8QItb7uBcfPjTCyMFuatVxf
